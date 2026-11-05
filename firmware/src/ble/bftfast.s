@ =============================================================================
@ bftfast.s - BLE: fast card reads over the Bluetooth link (paced transmission, streamed pieces, link settings)
@ (production image only, CF-08)
@
@ Why: the card requests of ble/bftsd.s answer one CHUNK per request, so every 232 bytes cost a full request round trip,
@ and the meter writes its answers to the BLE module at 19200 baud back to back (1920 bytes/s), faster than the module
@ forwards them (one 20-byte notification per connection event, about 1330 bytes/s): measured on a meter 2026-11-05,
@ answers above about 130 bytes lose bytes.  The firmware upload (host to meter) runs at about 1190 bytes/s; reads ran
@ at 184 bytes/s.  Here:
@   pacing   while the page Ld owns the link, the transmit pump of usart.s sends at most bfl_pace bytes per 10 ms tick
@            (bft_tick refills the budget, ble_tx_tick restarts the pump), so the module is never overrun, and an idle
@            frame after every bfl_gap bytes (ble_tx_gap), so the module does not misread bytes.
@   STREAM   the staged READ data is sent as consecutive pieces without a request per piece; the main loop (bfl_poll)
@            queues the next piece whenever the transmit queue has room.
@   LINK     pace, stop bits and a baud rate trim can be set at run time (RAM only, back to the defaults at the next
@            start) to measure what the module needs.
@
@ Measured on a meter (2026-11-05, 8 KiB streamed as 64-byte pieces, damaged bytes against the card file):
@     unpaced 1 stop bit             30 % of the bytes lost, the rest about every second byte damaged
@     pace 12                        nothing lost, 1 byte in 38 damaged
@     pace 12, 2 stop bits           1 byte in 70 .. 400 damaged (BRR trim -3 .. +8: no clear effect)
@     pace 4, 2 stop bits            1 byte in 9227 damaged, 352 bytes/s
@     pace 12, idle frame every 3    1 byte in 165 .. 710 damaged
@     pace 12 .. 14, idle frame every 2 bytes, 1 or 2 stop bits: no byte damaged in 12 runs (100 000 bytes);
@                                    with 232-byte pieces 1192 bytes/s of good data (pace 13; pace 14 no faster)
@     So the module misreads bytes that follow each other closely for longer than two characters; an idle frame
@     after every two bytes (3 character times per 2 bytes, at most 1280 bytes/s) stops that.  These are the
@     defaults (bfl_owner): pace 13, gap 2.

@ Requests (bft.s framing, answered with type 0x82 as ble/bftsd.s):
@     0x18 LINK    pace(1) stop(1) trim(1, signed) [gap(1)]   pace = bytes per 10 ms tick, 0 = unpaced (0 .. 64);
@                  stop = 1 or 2 stop bits; trim = BRR steps added to the BRR computed at the start of the link
@                  (-32 .. 32); gap = an idle frame after every gap bytes, 0 = none (0 .. 32; 0 if left out).
@                  field = the BRR that applies.  The new stop bits and BRR take effect once this answer has left.
@     0x19 STREAM  first(2) count(2) size(1)          pieces first .. first + count - 1 of size bytes (1 .. 232) of the
@                  staged data; count is cut at the end of the data.  field = number of pieces that follow.
@ Piece: B5 5B 83 idx(2) len(1) data(len) crc16(2), CRC-16/CCITT-FALSE over 83 .. data, as an answer.  Any other request
@     ends a stream and drops what is still queued of it.
@
@ No EEPROM, flash or card access in this module.
@ Context: main only, except bfl_tick_refill (TIM2 interrupt, through bft_tick).
@ =============================================================================

    .syntax unified
    .cpu cortex-m3
    .thumb
    .include "macros.inc"
    .include "hw.inc"
    .include "config.inc"

    .equ BFL_PACE_DEFAULT,  13              @ measured 2026-11-05 on a meter (below): 13 bytes per 10 ms tick
    .equ BFL_GAP_DEFAULT,   2               @ and an idle frame after every 2 bytes
    .equ BFL_PACE_MAX,      64
    .equ BFL_TRIM_MAX,      32
    .equ BFL_GAP_MAX,       32
    .equ BFL_PIECE_MAX,     232
    .equ BFL_T_PIECE,       0x83
    .equ BFX_ST_ARG,        0x22
    .equ USART_CR2_STOP_MASK, 0x3000
    .equ USART_CR2_STOP_2,  0x2000

    .equ bfl_stage,         v_20001240      @ log_buf, the staging buffer of bftsd.s
    .include "ram_v205.inc"

    .section .bss_port.bftfast, "aw", %nobits
    .balign 4
bfl_buf:        .space 8 + BFL_PIECE_MAX    @ piece being queued
bfl_next:       .space 2                    @ index of the next piece
bfl_left:       .space 2                    @ pieces still to queue (0: no stream)
bfl_base:       .space 2                    @ BRR before the first trim (0: not read yet)
bfl_new_brr:    .space 2                    @ BRR to apply
    .global bfl_pace
bfl_pace:       .space 1                    @ bytes per tick, 0 = unpaced (usart.s reads it in the pump; zero at start)
    .global bfl_gap
bfl_gap:        .space 1                    @ bytes between idle frames, 0 = none (usart.s)
    .global bfl_gapcnt
bfl_gapcnt:     .space 1                    @ bytes since the last idle frame (usart.s)
bfl_new_gap:    .space 1
    .global bfl_budget
bfl_budget:     .space 1                    @ bytes left in this tick (usart.s decrements, bft_tick refills)
bfl_size:       .space 1                    @ piece size of the stream
bfl_built:      .space 1                    @ bfl_buf holds piece bfl_next, not queued yet
bfl_pending:    .space 1                    @ new stop bits / BRR waiting for the answer to leave
bfl_new_stop:   .space 1                    @ 1 or 2

    .section .text.bftfast, "ax", %progbits

@ -----------------------------------------------------------------------------
@ bfl_tick_refill - new tick: refill the transmit budget
@ Clobbers : r0, r1
@ Context  : TIM2 interrupt (bft_tick, before ble_tx_tick restarts the pump)
@ -----------------------------------------------------------------------------
FUNC bfl_tick_refill
    ldr r1, =bfl_pace
    ldrb r0, [r1]
    ldr r1, =bfl_budget
    strb r0, [r1]
    bx lr
ENDFUNC bfl_tick_refill

@ -----------------------------------------------------------------------------
@ bfl_owner - the page Ld takes or gives up the link: transmit defaults
@ In       : r0 = 1 the page owns the link now, 0 it gave it up
@ Clobbers : r0-r2
@ Note     : taking it sets pace and gap to the defaults (a LINK of an earlier visit is forgotten); stop bits and BRR
@            are left as they are (a LINK may have changed them, the meter's start values otherwise).
@ -----------------------------------------------------------------------------
FUNC bfl_owner
    cbz r0, 1f
    movs r0, #BFL_PACE_DEFAULT
    ldr r1, =bfl_pace
    strb r0, [r1]
    movs r0, #BFL_GAP_DEFAULT
    ldr r1, =bfl_gap
    strb r0, [r1]
1:  movs r0, #0
    ldr r1, =bfl_left
    strh r0, [r1]
    ldr r1, =bfl_built
    strb r0, [r1]
    bx lr
ENDFUNC bfl_owner

@ -----------------------------------------------------------------------------
@ bfl_cancel - a request arrived: end a stream and drop its queued bytes
@ Clobbers : r0-r3, r12, flags
@ -----------------------------------------------------------------------------
FUNC bfl_cancel
    ldr r1, =bfl_left
    ldrh r0, [r1]
    ldr r2, =bfl_built
    ldrb r3, [r2]
    orrs r0, r0, r3
    movs r3, #0
    strh r3, [r1]
    strb r3, [r2]
    cbz r0, 1f                              @ no stream running: the queue holds answers only, keep them
    b ble_tx_queue_drop                     @ tail call
1:  bx lr
ENDFUNC bfl_cancel

@ -----------------------------------------------------------------------------
@ bfl_link - LINK request: pace, stop bits, baud rate trim
@ In       : bft_pkt (payload pace(1) stop(1) trim(1))
@ Out      : r0 = status, r1 = field (the BRR that applies), r2 = 0
@ Clobbers : r0-r3, r12, flags
@ -----------------------------------------------------------------------------
FUNC bfl_link
    push {r4, lr}
    ldr r3, =bft_pkt
    ldrb r0, [r3, #5]
    movs r1, #0                             @ gap 0 when the payload has 3 bytes
    cmp r0, #3
    beq 0f
    cmp r0, #4
    bne .Lln_arg
    ldrb r1, [r3, #9]                       @ gap
    cmp r1, #BFL_GAP_MAX
    bhi .Lln_arg
0:  ldr r0, =bfl_new_gap
    strb r1, [r0]
    ldrb r4, [r3, #6]                       @ pace
    cmp r4, #BFL_PACE_MAX
    bhi .Lln_arg
    ldrb r0, [r3, #7]                       @ stop bits
    subs r1, r0, #1
    cmp r1, #1
    bhi .Lln_arg                            @ not 1 or 2
    ldrsb r2, [r3, #8]                      @ trim
    adds r1, r2, #BFL_TRIM_MAX
    cmp r1, #(2 * BFL_TRIM_MAX)
    bhi .Lln_arg
    ldr r1, =bfl_new_stop
    strb r0, [r1]
    ldr r1, =bfl_base
    ldrh r0, [r1]
    cbnz r0, 1f
    ldr r0, =USART2_BASE
    ldrh r0, [r0, #USART_BRR]               @ first trim: remember the BRR of the link start
    strh r0, [r1]
1:  adds r0, r0, r2
    ldr r1, =bfl_new_brr
    strh r0, [r1]
    ldr r1, =bfl_pace
    strb r4, [r1]
    ldr r1, =bfl_new_gap
    ldrb r1, [r1]
    ldr r2, =bfl_gap
    strb r1, [r2]
    movs r1, #1
    ldr r2, =bfl_pending
    strb r1, [r2]
    mov r1, r0                              @ field = BRR
    movs r0, #0
    movs r2, #0
    pop {r4, pc}
.Lln_arg:
    movs r0, #BFX_ST_ARG
    movs r1, #0
    movs r2, #0
    pop {r4, pc}
ENDFUNC bfl_link

@ -----------------------------------------------------------------------------
@ bfl_stream - STREAM request: queue pieces of the staged data
@ In       : bft_pkt (payload first(2) count(2) size(1))
@ Out      : r0 = status, r1 = field (pieces that follow), r2 = 0
@ Clobbers : r0-r3, r12, flags
@ -----------------------------------------------------------------------------
FUNC bfl_stream
    push {r4-r6, lr}
    ldr r3, =bft_pkt
    ldrb r0, [r3, #5]
    cmp r0, #5
    bne .Lst_arg
    ldrb r4, [r3, #6]
    ldrb r0, [r3, #7]
    orr r4, r4, r0, lsl #8                  @ r4 = first
    ldrb r5, [r3, #8]
    ldrb r0, [r3, #9]
    orr r5, r5, r0, lsl #8                  @ r5 = count
    ldrb r6, [r3, #10]                      @ r6 = size
    subs r0, r6, #1
    cmp r0, #(BFL_PIECE_MAX - 1)
    bhi .Lst_arg
    ldr r0, =bfx_staged
    ldrh r0, [r0]                           @ staged bytes
    adds r0, r0, r6
    subs r0, r0, #1
    udiv r0, r0, r6                         @ pieces in the staged data
    subs r0, r0, r4                         @ pieces from first on
    ble .Lst_arg                            @ nothing there (or nothing staged)
    cmp r5, r0
    it hi
    movhi r5, r0                            @ cut at the end
    cbz r5, .Lst_arg
    ldr r0, =bfl_next
    strh r4, [r0]
    ldr r0, =bfl_size
    strb r6, [r0]
    ldr r0, =bfl_built
    movs r1, #0
    strb r1, [r0]
    ldr r0, =bfl_left
    strh r5, [r0]                           @ bfl_poll queues them after this answer
    movs r0, #0
    mov r1, r5
    movs r2, #0
    pop {r4-r6, pc}
.Lst_arg:
    movs r0, #BFX_ST_ARG
    movs r1, #0
    movs r2, #0
    pop {r4-r6, pc}
ENDFUNC bfl_stream

@ -----------------------------------------------------------------------------
@ bfl_poll - main-loop step while the page Ld owns the link: apply a LINK change, queue stream pieces
@ Clobbers : r0-r3, r12, flags (AAPCS)
@ Context  : main only (bft_poll)
@ -----------------------------------------------------------------------------
FUNC bfl_poll
    push {r4-r6, lr}
    ldr r0, =bfl_pending
    ldrb r0, [r0]
    cbz r0, .Lpl_stream
    @ apply once the queue is empty and the last byte has left the shift register
    ldr r0, =ble_txq_head
    ldrb r0, [r0]
    ldr r1, =ble_txq_tail
    ldrb r1, [r1]
    cmp r0, r1
    bne .Lpl_stream
    ldr r0, =ble_tx_state
    ldrb r0, [r0]
    cbnz r0, .Lpl_stream
    ldr r4, =USART2_BASE
    ldrh r0, [r4, #USART_SR]
    tst r0, #USART_SR_TC
    beq .Lpl_stream
    mrs r6, primask
    cpsid i
    ldrh r0, [r4, #USART_CR1]
    bic r0, r0, #USART_CR1_UE
    strh r0, [r4, #USART_CR1]               @ USART off while the frame format changes (RM0038 27.6.5, 27.6.3)
    ldrh r1, [r4, #USART_CR2]
    bic r1, r1, #USART_CR2_STOP_MASK
    ldr r2, =bfl_new_stop
    ldrb r2, [r2]
    cmp r2, #2
    it eq
    orreq r1, r1, #USART_CR2_STOP_2
    strh r1, [r4, #USART_CR2]
    ldr r2, =bfl_new_brr
    ldrh r2, [r2]
    strh r2, [r4, #USART_BRR]
    orr r0, r0, #USART_CR1_UE
    strh r0, [r4, #USART_CR1]
    msr primask, r6
    movs r0, #0
    ldr r1, =bfl_pending
    strb r0, [r1]
.Lpl_stream:
    ldr r0, =bfx_staged
    ldrh r0, [r0]
    cbnz r0, 1f
    ldr r1, =bfl_left
    strh r0, [r1]                           @ the staged data is gone (page left): no stream
    b .Lpl_ret
1:  ldr r0, =bfl_left
    ldrh r0, [r0]
    cmp r0, #0
    beq .Lpl_ret
    ldr r0, =bfl_built
    ldrb r0, [r0]
    cmp r0, #0
    bne .Lpl_put
    @ build piece bfl_next
    ldr r0, =bfl_size
    ldrb r5, [r0]                           @ r5 = size
    ldr r0, =bfl_next
    ldrh r4, [r0]                           @ r4 = idx
    mul r1, r4, r5                          @ r1 = offset
    ldr r2, =bfx_staged
    ldrh r2, [r2]
    subs r2, r2, r1                         @ bytes from the offset on (> 0: bfl_stream cut the count)
    cmp r2, r5
    it hi
    movhi r2, r5                            @ r2 = length of this piece
    mov r5, r2
    ldr r6, =bfl_buf
    movs r0, #0xB5
    strb r0, [r6, #0]
    movs r0, #0x5B
    strb r0, [r6, #1]
    movs r0, #BFL_T_PIECE
    strb r0, [r6, #2]
    strb r4, [r6, #3]
    lsrs r0, r4, #8
    strb r0, [r6, #4]
    strb r5, [r6, #5]
    ldr r3, =bfl_stage
    adds r3, r3, r1                         @ source
    adds r0, r6, #6
    mov r12, r5
2:  ldrb r2, [r3], #1
    strb r2, [r0], #1
    subs r12, r12, #1
    bne 2b
    adds r0, r6, #2
    adds r1, r5, #4                         @ type, idx(2), len, data
    bl bft_crc16
    adds r1, r6, r5
    strb r0, [r1, #6]
    lsrs r0, r0, #8
    strb r0, [r1, #7]
    ldr r0, =bfl_built
    movs r1, #1
    strb r1, [r0]
.Lpl_put:
    ldr r6, =bfl_buf
    ldrb r1, [r6, #5]
    adds r1, r1, #8
    mov r0, r6
    bl ble_tx_queue_put
    cbnz r0, .Lpl_ret                       @ no room yet: next pass
    ldr r0, =bfl_built
    movs r1, #0
    strb r1, [r0]
    ldr r0, =bfl_next
    ldrh r1, [r0]
    adds r1, r1, #1
    strh r1, [r0]
    ldr r0, =bfl_left
    ldrh r1, [r0]
    subs r1, r1, #1
    strh r1, [r0]
    b .Lpl_stream                           @ as many as fit
.Lpl_ret:
    pop {r4-r6, pc}
ENDFUNC bfl_poll
    .ltorg

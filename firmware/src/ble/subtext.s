@ =============================================================================
@ subtext.s - BLE: the sub-display text of the SETUP pages as an extra frame (custom CF-07, CUSTOM_CHANGES.md)
@
@ The 19-byte status frame describes the secondary display only through a v2.05 code in bytes 9..12, and only for the
@ setup items v2.05 knew (0, 1, 2, 4, 5, 6, 7, 10, 11, 12).  Every other page sends zeros there: the v2.05 items 3 (beeper),
@ 8 (ID) and 9 (logging interval), the MEM view (100) and all pages of the open firmware (bL, bt, rEL, tc, dSP, bH, CL,
@ Lt, Lo, HI, tr, Ch, n, Sd, tHI, tLo, the verdict, LP, Pt).  A Bluetooth app therefore cannot tell what the meter
@ shows.  The 19-byte frame stays exactly as it is (v2.05 apps keep working); instead, while a setup page is shown, a
@ separate 11-byte frame carries what the sub display shows:
@
@     FA item c0 c1 c2 c3 c4 flags units 00 xor
@       item   set_item (0x20008037): the page (1..39, 100 = MEM view); 0 = back to the normal display (sent once)
@       c0..c4 the five characters drawn at the sub-display positions 0..4, as lcd_draw_glyph got them (ASCII; ' ',
@              '-', '=', 0xFF all segments)
@       flags  bits 0..2 decimal point d (0 none, d = 1..4 digits after it, lcd_sub_dp), bit 4 sub minus sign, bit 5 the
@              page is being edited (set_edit)
@       units  sub-display unit icons: bit 0 V, 1 A, 2 m, 3 k, 4 Hz, 5 dB, 6 Ohm
@       xor    XOR of the ten bytes before it (the XOR of all eleven bytes is zero)
@
@ It is queued after a status frame is built (fn_0800C5D2) and sent between status frames (ble_tx_queue_put, as the
@ command echoes and the version answer); an app that does not know 0xFA skips it as it skips those.  Sent when anything
@ in it changes, else again every SUBTXT_REFRESH builds so that an app that connects on a page learns it.  While the
@ page value blinks during an edit, the blank phase (set_edit and not set_edit_blink, fn_0801797C) keeps the text of
@ the last visible phase.  Not sent on the page Ld (item 39), which owns the link for the file transfer.
@
@ Context: main only (lcd_draw_glyph and fn_0800C5D2 run in main).
@ =============================================================================

    .syntax unified
    .cpu cortex-m3
    .thumb
    .include "macros.inc"
    .include "hw.inc"
    .include "ram_v205.inc"
    .include "config.inc"

    .equ st_item,           v_20008037      @ set_item / ble_item
    .equ st_edit,           v_2000806E      @ set_edit
    .equ st_edit_blink,     v_2000806F      @ set_edit_blink (0 = blank phase while set_edit)
    .equ SUBTXT_START,      0xFA            @ first byte (C-1.03 used 0xF7, which zombu4's v1.0.4 gave to the
                                            @ bootloader version answer, ble/blcmd.s)
    .equ SUBTXT_LEN,        11
    .equ SUBTXT_REFRESH,    4               @ builds between repeats of an unchanged frame
    .equ SUBTXT_ITEM_BFT,   39              @ page Ld: no extra frames

    .section .bss_port.subtext, "aw", %nobits
@ ble_sub_chars: the characters last drawn at the sub-display positions 0..4 (written by lcd_draw_glyph)
    .global ble_sub_chars
ble_sub_chars:  .space 5
@ ble_sub_vis: the five characters, flags and units of the last visible phase
ble_sub_vis:    .space 7
@ ble_sub_frame: the frame being built; ble_sub_last: the last frame queued (item 0 after reset: nothing to say)
ble_sub_frame:  .space 12
ble_sub_last:   .space 12
ble_sub_cnt:    .space 1

    .section .text.ble.subtext, "ax", %progbits

@ -----------------------------------------------------------------------------
@ ble_subtext_frame - queue the sub-display text frame (FA) when it changed or is due again
@ Replaces : nothing in v2.05 (new; called by fn_0800C5D2 after build_status_packet_19b)
@ In/Out   : - / -
@ Clobbers : r0-r3, r12, flags (AAPCS)
@ Context  : main only
@ RAM      : reads ble_sub_chars, lcd_shadow, set_item, set_edit, set_edit_blink; writes ble_sub_vis, ble_sub_frame,
@            ble_sub_last, ble_sub_cnt; ble_tx_queue_put
@ -----------------------------------------------------------------------------
FUNC ble_subtext_frame
    push {r4, r5, r6, lr}
    ldr r0, =st_item
    ldrb r5, [r0]                           @ r5 = item
    cmp r5, #SUBTXT_ITEM_BFT
    beq .Lsx_ret                            @ page Ld owns the link
    ldr r4, =ble_sub_frame
    cbnz r5, .Lsx_page
    @ item 0: tell the app once that the setup page has gone
    ldr r0, =ble_sub_last
    ldrb r0, [r0, #1]
    cmp r0, #0
    beq .Lsx_ret                            @ already told (or never on a page)
.Lsx_page:
    @ the visible phase updates ble_sub_vis; the blank phase of an edit keeps it
    ldr r0, =st_edit
    ldrb r0, [r0]
    cbz r0, .Lsx_visible
    ldr r0, =st_edit_blink
    ldrb r0, [r0]
    cmp r0, #0
    beq .Lsx_build                          @ blank phase
.Lsx_visible:
    ldr r0, =ble_sub_chars
    ldr r1, =ble_sub_vis
    movs r2, #0
1:  ldrb r3, [r0, r2]
    strb r3, [r1, r2]
    adds r2, r2, #1
    cmp r2, #5
    blt 1b
    ldr r6, =lcd_shadow
    ldr r0, [r6, #0]                        @ w0: sub decimal points, m, dB
    movs r2, #0
    tst r0, #(1 << 21)
    it ne
    movne r2, #1
    tst r0, #(1 << 23)
    it ne
    movne r2, #2
    tst r0, #(1 << 25)
    it ne
    movne r2, #3
    tst r0, #(1 << 27)
    it ne
    movne r2, #4
    ldr r3, [r6, #16]                       @ w4: sub minus, k
    tst r3, #(1 << 29)
    it ne
    orrne r2, r2, #0x10
    strb r2, [r1, #5]                       @ flags (the edit bit is added below)
    movs r2, #0
    ldr r3, [r6, #8]                        @ w2: V, A
    tst r3, #(1 << 17)
    it ne
    orrne r2, r2, #0x01                     @ V
    tst r3, #(1 << 18)
    it ne
    orrne r2, r2, #0x02                     @ A
    tst r0, #(1 << 18)
    it ne
    orrne r2, r2, #0x04                     @ m
    ldr r3, [r6, #16]
    tst r3, #(1 << 17)
    it ne
    orrne r2, r2, #0x08                     @ k
    ldr r3, [r6, #24]                       @ w6: Hz, Ohm
    tst r3, #(1 << 17)
    it ne
    orrne r2, r2, #0x10                     @ Hz
    tst r0, #(1 << 19)
    it ne
    orrne r2, r2, #0x20                     @ dB
    tst r3, #(1 << 18)
    it ne
    orrne r2, r2, #0x40                     @ Ohm
    strb r2, [r1, #6]                       @ units
.Lsx_build:
    movs r0, #SUBTXT_START
    strb r0, [r4, #0]
    strb r5, [r4, #1]
    ldr r1, =ble_sub_vis
    movs r2, #0
2:  ldrb r3, [r1, r2]
    adds r0, r2, #2
    strb r3, [r4, r0]                       @ frame bytes 2..8 = characters, flags, units
    adds r2, r2, #1
    cmp r2, #7
    blt 2b
    ldr r0, =st_edit
    ldrb r0, [r0]
    cbz r0, 3f
    ldrb r0, [r4, #7]
    orr r0, r0, #0x20                       @ being edited
    strb r0, [r4, #7]
3:  movs r0, #0
    strb r0, [r4, #9]
    movs r2, #0                             @ XOR of bytes 0..9
    movs r1, #0
4:  ldrb r3, [r4, r1]
    eors r2, r2, r3
    adds r1, r1, #1
    cmp r1, #10
    blt 4b
    strb r2, [r4, #10]
    @ changed since the last frame queued?
    ldr r6, =ble_sub_last
    movs r1, #0
5:  ldrb r2, [r4, r1]
    ldrb r3, [r6, r1]
    cmp r2, r3
    bne .Lsx_send
    adds r1, r1, #1
    cmp r1, #SUBTXT_LEN
    blt 5b
    cbz r5, .Lsx_ret                        @ item 0 unchanged: said once
    ldr r1, =ble_sub_cnt
    ldrb r0, [r1]
    adds r0, r0, #1
    strb r0, [r1]
    cmp r0, #SUBTXT_REFRESH
    blo .Lsx_ret                            @ unchanged and not due yet
.Lsx_send:
    movs r0, r4
    movs r1, #SUBTXT_LEN
    bl ble_tx_queue_put                     @ r0 = 0 queued, 1 refused (link down or queue full: try at the next build)
    cbnz r0, .Lsx_ret
    ldr r6, =ble_sub_last
    movs r1, #0
6:  ldrb r2, [r4, r1]
    strb r2, [r6, r1]
    adds r1, r1, #1
    cmp r1, #SUBTXT_LEN
    blt 6b
    movs r0, #0
    ldr r1, =ble_sub_cnt
    strb r0, [r1]
.Lsx_ret:
    pop {r4, r5, r6, pc}
ENDFUNC ble_subtext_frame
    .ltorg

@ =============================================================================
@ setgoto.s - BLE: go straight to a SETUP page (custom CF-09)
@
@ Why: over Bluetooth an app can only press keys, and the SETUP pages are a loop of up to 40 pages with the page Ld in
@ the middle.  On Ld the received bytes belong to the file transfer (ble/bft.s), so a SETUP key frame from the app is
@ not seen there: an app could never step past Ld, and from a page before Ld never back to the normal display.
@
@ Request: a key frame (F4 hi lo hi lo, ble/commands.s) with the code 0xC0 + item, item 0 (the normal display) .. 40
@ (codes 0xC0 .. 0xE8).  The meter echoes it as every key frame.  It then steps the SETUP menu with the routine of the
@ SETUP key (fn_08015410) until the item is shown, inside one call: the pages on the way are never displayed, the page
@ Ld is not entered on the way (bft_poll only sees the item it stops at).  The same refusals as the SETUP key (double
@ beep, nothing changes): the power-on key window, logging, the MEM view, calibration mode; and an item that the
@ present function and state do not have (the menu came round to the page it started on), or a code above 0xE8.  On
@ success one beep, as a SETUP press, and the page is redrawn; an edit in progress ends without saving, as with the
@ SETUP key.  The page-text frame (ble/subtext.s, CF-07) then reports the new page; the auto power-off counter is
@ reloaded as for any key.
@
@ Older firmware passes codes 0xC0 .. 0xE8 to the key routine, whose decoder knows none of them (an app sends them
@ only to C-1.08 and later).
@
@ No EEPROM, flash or card access.  Context: main only (fn_0800C332, loop step 11).
@ =============================================================================

    .syntax unified
    .cpu cortex-m3
    .thumb
    .include "macros.inc"
    .include "hw.inc"
    .include "ram_v205.inc"
    .include "config.inc"
    .include "key.inc"

    .equ SG_ITEM_MAX,   40                  @ the highest setup item (For, IMP-32)
    .equ SG_STEPS_MAX,  64                  @ more than one round of the menu in any state
    .equ sg_redraw,     v_20008062          @ redraw request of the setup page (as the SETUP key, short.s)

    .text

@ -----------------------------------------------------------------------------
@ set_goto - step the SETUP menu to an item
@ In       : r0 = the item (0 = normal display .. SG_ITEM_MAX)
@ Out      : -
@ Clobbers : r0-r3, r12, flags (r4-r7 saved)
@ Context  : main only
@ RAM      : reads key_window, key_logging, key_mem_view, key_cal_mode; key_setup_item through fn_08015410; writes
@            sg_redraw
@ -----------------------------------------------------------------------------
FUNC set_goto
    push {r4-r7, lr}
    mov r4, r0
    bl fn_0800ED26                          @ activity: reload the auto-power-off counter
    cmp r4, #SG_ITEM_MAX
    bhi .Lsg_refuse
    ldr r0, =key_window
    ldrh r0, [r0]
    cmp r0, #0
    bne .Lsg_refuse                         @ power-on key window: SETUP has other meanings there
    ldr r0, =key_logging
    ldrb r0, [r0]
    ldr r1, =key_mem_view
    ldrb r1, [r1]
    orrs r0, r1
    ldr r1, =key_cal_mode
    ldrb r1, [r1]
    orrs r0, r1
    bne .Lsg_refuse                         @ logging, MEM view, calibration mode: the SETUP key is refused too
    ldr r5, =key_setup_item
    ldrb r6, [r5]                           @ r6 = the page shown now
    cmp r6, r4
    beq .Lsg_ok                             @ already there
    movs r7, #SG_STEPS_MAX
1:  bl fn_08015410                          @ the SETUP key's step to the next item
    ldrb r0, [r5]
    cmp r0, r4
    beq .Lsg_ok
    cmp r0, r6
    beq .Lsg_round                          @ round the menu: this item does not exist now
    subs r7, #1
    bne 1b
.Lsg_round:
    movs r0, #1
    ldr r1, =sg_redraw
    strb r0, [r1]
.Lsg_refuse:
    bl fn_0800EE6C                          @ refusal beep
    pop {r4-r7, pc}
.Lsg_ok:
    bl fn_0800EE50                          @ accept beep
    movs r0, #1
    ldr r1, =sg_redraw
    strb r0, [r1]                           @ redraw the setup page
    pop {r4-r7, pc}
ENDFUNC set_goto
    .ltorg

@ -----------------------------------------------------------------------------
@ bfg_request - card-protocol request 0x1C SETPAGE item(1) (ble/bftsd.s): set_goto from the page Ld, where the key
@               frames do not reach the key parser (the received bytes belong to the transfer, ble/bft.s)
@ In       : bft_pkt (payload: item(1), 0 .. SG_ITEM_MAX)
@ Out      : r0 = status (0, or 0x22 for a wrong payload), r1 = field (the item shown afterwards: the requested one,
@            or the old one when set_goto refused), r2 = 0
@ Clobbers : r0-r3, r12, flags
@ Note     : the answer is queued by bfx_reply before the next bft_poll sees that the page Ld was left
@ -----------------------------------------------------------------------------
FUNC bfg_request
    push {r4, lr}
    ldr r3, =bft_pkt
    ldrb r0, [r3, #5]
    cmp r0, #1
    bne .Lbg_arg
    ldrb r0, [r3, #6]
    cmp r0, #SG_ITEM_MAX
    bhi .Lbg_arg
    bl set_goto
    ldr r1, =key_setup_item
    ldrb r1, [r1]
    movs r0, #0
    movs r2, #0
    pop {r4, pc}
.Lbg_arg:
    movs r0, #0x22                          @ BFX_ST_ARG
    movs r1, #0
    movs r2, #0
    pop {r4, pc}
ENDFUNC bfg_request
    .ltorg

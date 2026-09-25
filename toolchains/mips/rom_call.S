/* Native-to-ROM call probe: a CanGoTo override that calls the ROM operation
 * Name(self) through the object-method dispatcher, then returns true.
 *
 * Calling form taken from Ne2000.pkg code (file offset 14516 onward) and
 * SeparatePackageLib.o __DispatchObjectMethod: t7 = operation selector,
 * a0 = receiver, jump to the dispatcher address the loader stored in the
 * package globals; $gp is saved and restored around the call.  The selector
 * is the SystemPublic ordinal + 1 (CanGoTo 4319 dispatched as t7 = 0x10E0).
 * Globals word 0 is filled by an initialization entry: source kind 6,
 * interface "Dispatchers", index 1 (object methods), destination mode 4.
 * The first 16 bytes of the frame are the o32 argument home area.
 */
.set noreorder
.set noat
.text
.globl rosemary_can_go_to
.type rosemary_can_go_to, @function
.ent rosemary_can_go_to
rosemary_can_go_to:
    addiu   $sp, $sp, -32
    sw      $ra, 28($sp)
    sw      $gp, 24($sp)
    sw      $16, 20($sp)
    move    $16, $4
    lw      $25, 0($gp)           /* __DispatchObjectMethod entry point */
    addiu   $15, $zero, 4187      /* Name: SystemPublic operation 4186 + 1 */
    jalr    $25
    nop
    lw      $gp, 24($sp)
    lw      $ra, 28($sp)
    lw      $16, 20($sp)
    addiu   $2, $zero, 1
    jr      $ra
    addiu   $sp, $sp, 32
.end rosemary_can_go_to
.size rosemary_can_go_to, .-rosemary_can_go_to

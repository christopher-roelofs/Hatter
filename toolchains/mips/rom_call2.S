/* Second native-to-ROM probe: arguments and an intrinsic.
 *   name = Name(self)            object dispatcher, selector 4187, result v0
 *   SetName(self, name)          object dispatcher, selector 4188, a1 = name
 *   Honk()                       intrinsic dispatcher, selector 77 (the
 *                                literal in PublicInterface.cdef), no receiver
 * Globals: word 0 = Dispatchers index 0 (intrinsics), word 1 = index 1
 * (object methods).  $gp is restored after every ROM call.
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
    sw      $17, 16($sp)
    move    $16, $4
    lw      $25, 4($gp)
    addiu   $15, $zero, 4187      /* Name */
    jalr    $25
    nop
    lw      $gp, 24($sp)
    move    $17, $2               /* keep the name */
    lw      $25, 4($gp)
    move    $4, $16
    move    $5, $17
    addiu   $15, $zero, 4188      /* SetName(self, name) */
    jalr    $25
    nop
    lw      $gp, 24($sp)
    lw      $25, 0($gp)
    addiu   $15, $zero, 77        /* Honk() */
    jalr    $25
    nop
    lw      $gp, 24($sp)
    lw      $ra, 28($sp)
    lw      $16, 20($sp)
    lw      $17, 16($sp)
    addiu   $2, $zero, 1
    jr      $ra
    addiu   $sp, $sp, 32
.end rosemary_can_go_to
.size rosemary_can_go_to, .-rosemary_can_go_to

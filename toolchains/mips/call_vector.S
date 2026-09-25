/* Research probe: one uint32 argument/result, not a general ABI bridge.
 * a0 = address of {codeAddress, globalPointer}; a1 = argument.
 * Layout/call sequence: SDK Generic.h and SeparatePackageLib.o.
 */
.set noreorder
.set noat
.text
.globl rosemary_call_u32
.ent rosemary_call_u32
rosemary_call_u32:
    addiu $sp, $sp, -32
    sw $ra, 28($sp)
    sw $gp, 16($sp)
    lw $25, 0($4)
    lw $gp, 4($4)
    addu $4, $5, $zero
    jalr $25
    nop
    lw $gp, 16($sp)
    lw $ra, 28($sp)
    addiu $sp, $sp, 32
    jr $ra
    nop
.end rosemary_call_u32

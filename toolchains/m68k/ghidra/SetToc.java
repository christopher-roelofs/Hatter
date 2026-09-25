// Tell Ghidra what r2 holds, which is what CFM sets from the main TVector.
// @category MagicCap
import ghidra.app.script.GhidraScript;
import ghidra.program.model.lang.Register;
import ghidra.program.model.mem.MemoryBlock;
import java.math.BigInteger;
public class SetToc extends GhidraScript {
    @Override public void run() throws Exception {
        long toc = Long.parseLong(getScriptArgs()[0], 16);
        Register r2 = currentProgram.getRegister("r2");
        int blocks = 0;
        for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
            if (!b.isExecute()) continue;
            currentProgram.getProgramContext().setValue(
                    r2, b.getStart(), b.getEnd(), BigInteger.valueOf(toc));
            println("set r2=" + Long.toHexString(toc) + " over " + b.getName()
                    + " " + b.getStart() + ".." + b.getEnd());
            blocks++;
        }
        println("blocks set: " + blocks);
    }
}

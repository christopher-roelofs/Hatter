// Locate a message in memory by its bytes and report what reaches it.
// @category MagicCap

import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import java.io.*;
import java.util.*;

public class FindMsg extends GhidraScript {

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outDir = args[0];
        new File(outDir).mkdirs();

        for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
            println("BLOCK " + b.getName() + " " + b.getStart() + ".." + b.getEnd()
                    + " init=" + b.isInitialized() + " x=" + b.isExecute());
        }

        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        PrintWriter out = new PrintWriter(new File(outDir, "found.c"));

        for (int i = 1; i < args.length; i++) {
            byte[] needle = args[i].getBytes("ISO-8859-1");
            Address at = currentProgram.getMemory().findBytes(
                    currentProgram.getMinAddress(), needle, null, true, monitor);
            println("MSG " + quote(args[i]) + " -> " + at);
            if (at == null) continue;
            Set<Function> seen = new LinkedHashSet<>();
            // References straight at the string, and at the word before it --
            // a TOC entry pointing at it lands on its own address.
            for (Address probe : new Address[]{at, at.subtract(1), at.subtract(2),
                                               at.subtract(3), at.subtract(4)}) {
                for (Reference r : currentProgram.getReferenceManager()
                        .getReferencesTo(probe)) {
                    Function f = currentProgram.getFunctionManager()
                            .getFunctionContaining(r.getFromAddress());
                    println("   ref from " + r.getFromAddress() + " "
                            + (f == null ? "(none)" : f.getName() + " @" + f.getEntryPoint()));
                    if (f != null) seen.add(f);
                }
            }
            for (Function f : seen) {
                out.println("/* ==== " + f.getName() + " @" + f.getEntryPoint()
                            + "  reached " + quote(args[i]) + " ==== */");
                DecompileResults res = decomp.decompileFunction(f, 180, monitor);
                out.println(res.decompileCompleted()
                            ? res.getDecompiledFunction().getC()
                            : "/* failed: " + res.getErrorMessage() + " */");
                out.println();
            }
        }
        out.close();
        decomp.dispose();
        println("wrote " + new File(outDir, "found.c"));
    }

    private static String quote(String s) {
        return "\"" + (s.length() > 60 ? s.substring(0, 60) + "..." : s) + "\"";
    }
}

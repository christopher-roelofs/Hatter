// Decompile the largest functions, to see what the decompiler makes of this.
// @category MagicCap
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import java.io.*;
import java.util.*;
public class Decomp extends GhidraScript {
    @Override public void run() throws Exception {
        String out = getScriptArgs()[0];
        int want = Integer.parseInt(getScriptArgs()[1]);
        List<Function> fs = new ArrayList<>();
        for (Function f : currentProgram.getFunctionManager().getFunctions(true)) fs.add(f);
        fs.sort((a,b) -> Long.compare(b.getBody().getNumAddresses(), a.getBody().getNumAddresses()));
        DecompInterface d = new DecompInterface();
        d.openProgram(currentProgram);
        PrintWriter w = new PrintWriter(new File(out));
        for (int i = 0; i < Math.min(want, fs.size()); i++) {
            Function f = fs.get(i);
            w.println("/* ==== " + f.getName() + " @" + f.getEntryPoint()
                      + "  " + f.getBody().getNumAddresses() + " bytes ==== */");
            DecompileResults r = d.decompileFunction(f, 180, monitor);
            w.println(r.decompileCompleted() ? r.getDecompiledFunction().getC()
                                             : "/* failed */");
        }
        w.close(); d.dispose();
        println("decompiled " + Math.min(want, fs.size()) + " functions to " + out);
    }
}

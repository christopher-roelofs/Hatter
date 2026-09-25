// How much of this program did analysis actually connect up?
// @category MagicCap
import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
public class RefStats extends GhidraScript {
    @Override public void run() throws Exception {
        Program p = currentProgram;
        int strings = 0, stringsWithRefs = 0;
        DataIterator it = p.getListing().getDefinedData(true);
        while (it.hasNext()) {
            Data d = it.next();
            if (!(d.getValue() instanceof String)) continue;
            strings++;
            if (p.getReferenceManager().getReferenceCountTo(d.getAddress()) > 0) stringsWithRefs++;
        }
        println("defined strings " + strings + ", of which referenced " + stringsWithRefs);
        println("functions " + p.getFunctionManager().getFunctionCount());
        int named = 0;
        for (Function f : p.getFunctionManager().getFunctions(true))
            if (!f.getName().startsWith("FUN_")) named++;
        println("functions with a real name: " + named);
    }
}

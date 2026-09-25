/* First C-compiled package method: calls ROM operations and an intrinsic
 * through generated stubs, and keeps a counter in package globals. */
#include "mcap_probe.h"

static unsigned counter;
static const char text[] = "hello";

static int helper(int x) { return x * 3 + (int)counter; }

Method Boolean
Probe_CanGoTo(Reference self)
{
    Reference n = Name(self);
    SetName(self, n);
    counter += helper((int)n);
    if (text[0] == 'h')
        Honk();
    return 1;
}

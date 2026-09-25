/* Freestanding code-generation probe; no Magic Cap runtime dependencies. */
typedef unsigned int u32;
struct TransitionVector { u32 code_address; u32 global_pointer; };
_Static_assert(sizeof(void *) == 4, "32-bit target required");
_Static_assert(sizeof(struct TransitionVector) == 8, "two-word vector required");
u32 rosemary_add(u32 value) { return value + 7; }

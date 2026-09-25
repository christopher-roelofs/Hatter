# Starship Courier (MIPS prototype)

A smaller Magic Cap 3.x game project demonstrating a custom scene, grid-based
touch input, persistent object fields, and native drawing. The player can move,
intercept a drone, and reset. Enemy turns and obstacles are not implemented.

Build from the Hatter root:

```sh
python3 toolchains/mips/build_sample.py examples/mips/StarshipCourier --out out/StarshipCourier
```

The package is `out/StarshipCourier/StarshipCourier.pkg`. Source is in
`StarshipCourier.cpp`, class definitions in `StarshipCourier.cdef`, and object
instances in `Objects.odef`. Use [Magic Sokoban](../Sokoban/README.md) for a
more complete game example.

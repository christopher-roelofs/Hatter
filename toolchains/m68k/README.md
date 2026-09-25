# Reading 68k Magic Cap packages

`inspect_package.py` decodes the package container the original ObjectMaker
wrote for Magic Cap 1.0/1.5: the header, the object chain with class names,
and the 68k methods and their call sites. It is read-only, and it reports the
fields it has not established rather than naming them. See
[the container notes](../../docs/OBJECTMAKER_FORMAT.md) for the format and for
what is still unread.

From the project root:

```sh
python3 toolchains/m68k/inspect_package.py \
    software/68k/extracted/installable/cookbook/Counter.pkg
python3 toolchains/m68k/inspect_package.py --code \
    software/68k/extracted/installable/cookbook/Metric.pkg
python3 toolchains/m68k/inspect_package.py --fields \
    software/68k/extracted/installable/cookbook/Counter.pkg
python3 toolchains/m68k/inspect_package.py --json \
    software/68k/extracted/installable/cookbook/Counter.pkg

# Use the matching definitions when inspecting a 1.5 package:
python3 toolchains/m68k/inspect_package.py --profile 1.5 --fields \
    Counter-1.5.pkg

# Build against the preserved CW8 Magic Cap 1.5 interface profile:
python3 toolchains/m68k/build_example.py \
    "software/68k/extracted/cookbook/Cookbook Examples/Counter" \
    --profile 1.5 -o Counter-1.5.pkg
```

`build_example.py --profile` accepts `cw7` (the default), `1.0`, `1.5`,
`universal`, or an explicit interface directory. CW8 keeps its generated
system-interface headers in the precompiled-system-classes tree; the builder
locates those headers automatically. The profile controls class, operation,
intrinsic, and field definitions, so do not mix files from different profiles.
The output parent directory is created automatically, which makes profile
matrix builds such as `-o out/profiles/1.5/Counter.pkg` reproducible.

`--fields` reads each object as the fields its class declares, using
`classdefs.py`, which works out layouts from the SDK's class definitions and
the sizes its own `Types.Def` and headers give. A class it cannot resolve is
left as bytes rather than approximated.

Class, operation and intrinsic names come from the SDK's own number tables
under `software/68k/extracted`. Without them the decode is the same and the
numbers print bare.

The tests check the decode against what the cookbook examples say about
themselves -- their ObjectMaker definitions and their C -- rather than against
itself:

```sh
cd toolchains/m68k && python3 -m unittest test_inspect_package
```

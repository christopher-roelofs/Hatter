# 68k Magic Cap 1.0/1.5 packages

`build_example.py` builds a package from a cookbook-style project directory
containing `.Def` object/class definitions and, for code-bearing packages,
native C source. It uses the selected Magic Cap interface profile to generate
headers and package records.

Start from a preserved cookbook example, then copy and modify its source:

```sh
python3 toolchains/m68k/build_example.py \
  "software/68k/extracted/cookbook/Cookbook Examples/Counter" \
  --profile 1.5 -o out/Counter.pkg
```

Profiles are `cw7` (default), `1.0`, `1.5`, and `universal`; an explicit
interface directory is also accepted. Select a profile matching the guest ROM.
Do not mix 1.0 and 1.5 class/operation numbers. The separate
[68k Sokoban example](../../examples/68k/Sokoban/README.md) shows a larger
application and a shared-rules cross-target project.

Inspect the result before installation:

```sh
python3 toolchains/m68k/inspect_package.py --fields --code out/Counter.pkg
```

`inspect_package.py` is read-only. It decodes known package fields and native
methods and leaves unknown fields explicit. Run the host regression suite and
SDK sample builds with `scripts/test-toolchains`. See [setup](../../docs/SETUP.md)
for local SDK requirements and the [developer guide](../../docs/MAGIC_CAP_DEVELOPER_GUIDE.md)
for source conventions and object-model details.

The host build does not establish compatibility with every 68k ROM. Install
and exercise a package in the matching guest before shipping it.

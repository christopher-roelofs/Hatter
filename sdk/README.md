# Local Magic Cap SDK assets

This directory holds only the historical inputs needed to build and test
Hatter projects. Its contents are ignored by Git except for this map. Copy
them from the complete archives in the sibling `magicrecomp` repository when
setting up a fresh checkout; see [setup](../docs/SETUP.md).

```text
sdk/
  68k/
    interfaces/
      1.0-original/     original Magic Cap 1.0 headers and definitions
      1.0/              later Magic Cap 1.0 headers and definitions
      1.5/              Magic Cap 1.5 headers and definitions
      universal/        compatibility profile
      system/           generated headers shared by later profiles
    samples/projects/   original example projects
    samples/packages/   matching compiled packages for regression tests
    fixtures/           other reference packages for regression tests
  mips/
    Interfaces/          Apollo headers and package definitions
    Samples/             original sample projects
```

The installer and extraction directory names are deliberately not part of
this layout. The two 1.0 directories contain different interface revisions;
files with the same name are not always interchangeable. Precompiled binaries,
manifests, and historical compiler tools are not needed by the host builders.
The full original distributions remain in `magicrecomp`.

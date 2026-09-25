"""Host rules and package-build regressions for the native Sokoban sample."""
import shutil
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

SAMPLE = Path(__file__).resolve().parents[2] / "examples/mips/Sokoban"

class SokobanTests(unittest.TestCase):
    def test_branding_and_native_icon(self):
        objects = (SAMPLE / "Objects.odef").read_text()
        for declaration in ("SoftwarePackageContents contents", "Scene packageScene", "Icon gameIcon"):
            self.assertIn("instance " + declaration + " 'Magic Sokoban';", objects)
        self.assertIn("receiver: iGameRoomShelf;", objects)
        icon = objects.split("instance Image crateIcon;", 1)[1]
        self.assertIn("resolution: 256.s;", icon)
        self.assertIn("imageSize: 48,48;", icon)
        launcher = objects.split("instance Icon gameIcon", 1)[1].split("end instance;", 1)[0]
        self.assertIn("contentSize: <53.0,53.0>;", launcher)
        pixels = bytes.fromhex(re.search(r"data: \$ ([0-9a-f]+);", icon)[1])
        self.assertEqual(len(pixels), 48 * 48 * 2 // 8)
        preview = re.findall(r"// \|([ .o#]{48})\|", icon)
        self.assertEqual(len(preview), 48)
        decoded = "".join(" .o#"[(byte >> shift) & 3]
                          for byte in pixels for shift in (6, 4, 2, 0))
        self.assertEqual(decoded, "".join(preview))

    @unittest.skipUnless(shutil.which("g++"), "g++ required")
    def test_rules_and_all_level_solutions(self):
        with tempfile.TemporaryDirectory(prefix="sokoban-rules-") as tmp:
            exe = Path(tmp) / "rules-test"
            subprocess.run(["g++", "-std=c++98", "-Wall", "-Wextra", "-Werror",
                            str(SAMPLE / "tests" / "rules_test.cpp"), "-o", str(exe)], check=True)
            result = subprocess.run([str(exe)], check=True, capture_output=True, text=True)
            self.assertEqual(result.stdout.count("Level "), 12)

    @unittest.skipUnless(all(shutil.which(t) for t in
                            ("clang-18", "ld.lld-18", "llvm-objdump-18")), "LLVM 18 required")
    def test_package_with_source_local_rules_header(self):
        from build_sample import build_sample
        with tempfile.TemporaryDirectory(prefix="sokoban-package-") as tmp:
            raw, manifest = build_sample(SAMPLE, "Sokoban", Path(tmp))
            self.assertGreater(len(raw), 1000)
            self.assertEqual(len(manifest["methods"]), 5)
            self.assertIn("SokobanBoard_UndoMove", manifest["methods"])
            self.assertIn("iconInstaller", manifest["selectors"])

if __name__ == "__main__":
    unittest.main()

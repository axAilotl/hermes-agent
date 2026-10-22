"""Regression tests for the Hermes-managed Node's npm global prefix.

When the installer falls back to a bundled Node under ``$HERMES_HOME/node``,
npm's default global prefix is that Node dir, so ``npm install -g <pkg>``
drops the package binary in ``$HERMES_HOME/node/bin`` — which is NOT on PATH
(only the command link dir is) and is wiped on every Node upgrade. Users then
report "I can ``npm i -g`` but the package isn't usable on the command line".

The fix redirects the bundled Node's global prefix to the command link dir's
parent (so global bins land in the already-on-PATH link dir alongside
node/npm/npx), scoped to the bundled Node via its prefix-local global npmrc.
"""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"
NODE_BOOTSTRAP = REPO_ROOT / "scripts" / "lib" / "node-bootstrap.sh"


def test_install_sh_redirects_bundled_npm_global_prefix_to_link_dir() -> None:
    text = INSTALL_SH.read_text()

    # The redirect must target the link dir's PARENT so global bins resolve to
    # <parent>/bin == the command link dir (node/npm/npx live there and it is
    # guaranteed on PATH by the installer's PATH setup).
    assert "configure_managed_node_npm_prefix()" in text
    assert 'printf \'prefix=%s\\n\' "$(dirname "$link_dir")" > "$HERMES_HOME/node/etc/npmrc"' in text


def test_install_sh_repairs_existing_managed_node_on_rerun() -> None:
    """The redirect must run on every install (not just fresh Node installs),
    so re-running the installer repairs pre-existing managed installs whose
    Node is already up to date and would otherwise skip install_node."""
    text = INSTALL_SH.read_text()

    check_node_body = text.split("check_node()", 1)[1].split("\ninstall_node()", 1)[0]
    assert "configure_managed_node_npm_prefix" in check_node_body

    # No-op guard so it's safe to call when there is no managed Node.
    assert '[ -x "$HERMES_HOME/node/bin/npm" ] || return 0' in text


def test_node_bootstrap_redirects_bundled_npm_global_prefix_to_link_dir() -> None:
    text = NODE_BOOTSTRAP.read_text()

    assert "_nb_configure_npm_prefix()" in text
    assert 'printf \'prefix=%s\\n\' "$(dirname "$_link_dir")" > "$HERMES_HOME/node/etc/npmrc"' in text

    # Runs at the top of ensure_node so existing managed installs are repaired
    # even when a modern Node is already present (early return path).
    ensure_node_body = text.split("ensure_node()", 1)[1]
    assert "_nb_configure_npm_prefix" in ensure_node_body
    assert '[ -x "$HERMES_HOME/node/bin/npm" ] || return 0' in text
    assert "heal_managed_node()" in text
    assert "_nb_managed_tool_broken" in text
    assert "for tool in node npm npx" in text


def test_node_installers_require_supported_brotli_security_patches() -> None:
    """Old patch and prerelease binaries must not bypass installation checks."""
    import subprocess

    install = INSTALL_SH.read_text()
    predicate = "node_satisfies_build() {" + install.split("node_satisfies_build() {", 1)[1].split("\n}", 1)[0] + "\n}"
    versions = {
        "v20.20.2": False, "v22.23.3": False, "v22.23.4": True,
        "v22.24.0": True, "v23.11.1": False, "v24.22.0": False,
        "v24.22.1": True, "v25.9.0": False, "v26.12.0": False,
        "v26.12.1": True, "v24.22.1-rc.1": False, "garbage": False,
    }
    for version, accepted in versions.items():
        for source, function in [(predicate, "node_satisfies_build"),
                                  ('source "' + str(NODE_BOOTSTRAP) + '"', "_nb_node_version_secure")]:
            result = subprocess.run(["bash", "-c", source + '\n' + function + ' "$1"', "test", version], check=False)
            assert (result.returncode == 0) is accepted, (function, version)


def test_standalone_setup_and_nixos_guard_check_the_decoder() -> None:
    """Execute their actual JavaScript guards without installing any tools."""
    import subprocess

    scripts = [
        REPO_ROOT / "optional-skills/creative/hyperframes/scripts/setup.sh",
        REPO_ROOT / "nix/nixosModules.nix",
    ]
    for script in scripts:
        code = script.read_text().split("node -e '", 1)[1].split("\n", 1)[1]
        code = code.split("\n        '", 1)[0] if script.suffix == ".nix" else code.split("\n'; then", 1)[0]
        for version, constant, accepted in [
            ("22.23.3", -17, False), ("22.23.4", -17, True),
            ("24.22.0", -17, False), ("24.22.1", -17, True),
            ("26.12.0", -17, False), ("26.12.1", -17, True),
            ("24.22.1", None, False), ("24.22.1-rc.1", -17, False),
        ]:
            import json
            runner = "new Function('process', 'require', " + json.dumps(code) + ")({versions:{node: " + json.dumps(version) + "},exit: c=>process.exit(c)},()=>({constants:{BROTLI_DECODER_ERROR_FORMAT_BLOCK_SWITCH:" + json.dumps(constant) + "}}));"
            result = subprocess.run(["node", "-e", runner], check=False, capture_output=True)
            assert (result.returncode == 0) is accepted, (script, version, constant, result.stderr)


def test_nixos_refresh_retains_supported_installed_node_line() -> None:
    """APT must upgrade an old 24/26 install on its own channel, not stay old."""
    import subprocess

    text = (REPO_ROOT / "nix/nixosModules.nix").read_text()
    selector = 'case "$node_major" in' + text.split('case "$node_major" in', 1)[1].split("esac", 1)[0] + "esac"
    for major, expected in [("18", "22"), ("22", "22"), ("24", "24"), ("26", "26"), ("", "22")]:
        result = subprocess.run(["bash", "-c", 'node_major="$1"; ' + selector + '\nprintf %s "$node_major"', "test", major], check=True, capture_output=True, text=True)
        assert result.stdout == expected

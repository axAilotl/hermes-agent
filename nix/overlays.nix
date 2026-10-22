# nix/overlays.nix — Expose pkgs.hermes-agent for external NixOS configs
{ inputs, ... }:
{
  flake.overlays.default = final: _: {
    hermes-agent = final.callPackage ./hermes-agent.nix {
      inherit (inputs) uv2nix pyproject-nix pyproject-build-systems;
      nodejs_22 = inputs.nixpkgs-node.legacyPackages.${final.stdenv.hostPlatform.system}.nodejs_22;
      npm-lockfile-fix = inputs.npm-lockfile-fix.packages.${final.stdenv.hostPlatform.system}.default;
      rev = inputs.self.rev or null;
    };
  };
}

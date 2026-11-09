<!-- Fill in the changelog, delete this comment, then publish the draft. -->
## Changes

- TODO changelog bullets

## Notes

- **No game assets are included.** You must supply your own WWF WrestleMania 2000
  (USA) ROM — SHA1 `442D417A52ED672CA1A47E7261A5414DEBB1E27A`. On first
  launch, click **Load ROM** and select it; the launcher validates and remembers
  it. Modified ROMs (such as the "V1.2" fan hack) and other regions are not accepted.
- **Windows SmartScreen**: the exe is unsigned, so Windows may warn on first run.
  Click "More info" → "Run anyway".
- **Saves and settings** live in `%LOCALAPPDATA%\Wm2kRecompiled\` — both the cart
  save and the virtual Controller Pak persist automatically. Save data is
  compatible across releases unless a release note says otherwise. For a portable
  install, create an empty `portable.txt` next to the exe.
- **GPU**: D3D12 by default. If you hit rendering issues, update your GPU drivers
  first, and please attach `%LOCALAPPDATA%\Wm2kRecompiled\Wm2kRecompiled.log`
  to any bug report.
- Known issues are tracked in the README.

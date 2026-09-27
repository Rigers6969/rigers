# Tirana in Roblox

A hand-built road network of central Tirana and its surrounding
districts, for a Roblox driving game - real street names and real
relative geography, laid out from general knowledge of the city rather
than pulled from a live mapping API (this dev environment has no
outbound access to OpenStreetMap/Google Maps/etc. - see the note in
`RoadData.lua`'s docstring). Treat the layout as "recognizable and
correctly arranged," not survey-precise coordinates.

## What's here

- **`RoadData.lua`** - a ModuleScript with every road (name, type,
  width, and its path as a list of points) and every landmark. This is
  the only file you'd ever hand-edit to add/move roads.
- **`RoadBuilder.server.lua`** - a Script that reads `RoadData.lua` and
  builds it: a Part per road segment, a glowing pillar + floating name
  label per landmark, and a grass baseplate underneath everything.

## Covers

Central Tirana (Skanderbeg Square, the boulevard, Blloku, Mother Teresa
Square, the Grand Park) plus the main arteries extending out towards
Kombinat, Laprakë, Kamëz, Kashar/Rinas, Selitë, and Babrru - the outer
stretches and district placements are approximate corridor directions,
called out as such in `RoadData.lua`'s comments.

## Setup (in Roblox Studio, on your PC)

1. Open Roblox Studio, create a new empty place (Baseplate template is
   fine - `RoadBuilder.server.lua` adds its own ground).
2. In the Explorer, find **ServerScriptService**.
3. Right-click it -> **Insert Object** -> **ModuleScript**. Rename it
   exactly `RoadData`. Delete its default content, paste in everything
   from `RoadData.lua`.
4. Right-click ServerScriptService again -> **Insert Object** ->
   **Script**. Rename it anything you like (e.g. `RoadBuilder`).
   Delete its default content, paste in everything from
   `RoadBuilder.server.lua`. It must be a **sibling** of the
   `RoadData` ModuleScript (both directly inside ServerScriptService)
   - the script `require`s it by that relationship.
5. Press **Play** once. Check the Output window for
   `RoadBuilder: built N road segments and M landmarks.` - then stop
   Play. The roads/landmarks/ground are now permanent parts of your
   place (Play just triggers the Script to run once; you don't need to
   keep re-running it, and re-running it after editing `RoadData.lua`
   safely rebuilds from scratch instead of duplicating anything).
6. Fly around in Studio (right-click drag + WASD) to see the layout.

## Better buildings (replaces the city template's generator)

`BuildingGenerator.lua` is a drop-in replacement for the
`BuildingGenerator` ModuleScript that came with the city template - same
`Generate(parent)` function and same `CityConfiguration` settings, so
nothing else needs to change. Open your existing `BuildingGenerator`,
select all, delete, paste this file's contents in.

Instead of identical square blocks you get five building types
(colorful Tirana-style apartment blocks with balconies, stepped towers,
glass towers, shops with awnings, small parks with trees), each with
its own size and position inside its lot, and taller buildings toward
the middle of the map like a real downtown.

## Cars

| File | What to insert | Where |
|---|---|---|
| `CarSpawner.server.lua` | **Script** (any name) - the whole car system | ServerScriptService |
| `SpawnCarButton.client.lua` | **LocalScript** (any name) - the dealership UI | StarterPlayer > StarterPlayerScripts |

25 real cars, from a free used Mercedes 190E up to the ~$9M Bugatti
Centodieci. Each gets its real body type, signature color, and top
speed / acceleration scaled from its real specs. Prices are
approximate real new prices. Built from parts, so they're shaped like
their class (hatchback, sedan, SUV, luxury, sports, supercar,
hypercar) rather than exact replicas.

Then press Play:
- Your car appears next to you ~2 seconds after you spawn.
- **G** opens the dealership - buy cars or spawn ones you own.
- **C** respawns your current car in front of you.
- Walk up to a car and press **E**. **W/S** gas/brake/reverse,
  **A/D** steer, **Space** to get out.
- Driving earns cash (faster cars earn more per second).
- In Studio every car is free, for testing.

### Real car shapes (3D models)

Cars built from blocks can't look like the real thing - that needs a 3D
model. Any car can use one:

1. In the Explorer, right-click **ServerStorage** -> Insert Object ->
   **Folder**, name it exactly `CarModels`.
2. Open the **Toolbox** (View -> Toolbox), Models tab, search the car
   (e.g. "Bugatti Chiron"). Click one to insert it.
3. Drag it from Workspace into the `CarModels` folder and rename it to
   that car's id (below - the dealership also shows each car's id).
4. Play and spawn it. The game resizes it, points it forward, puts its
   wheels on the road, and removes any scripts/seats it came with.
5. If it drives backwards: select the model in `CarModels` ->
   Properties -> Attributes -> **+** -> name `YawOffset`, type Number,
   value `180` (or `90` if it drives sideways).

Car ids: `mercedes190e`, `sandero`, `corolla`, `civic`, `golfgti`,
`mustang`, `cclass`, `bmwm3`, `teslaplaid`, `rangerover`, `porsche911`,
`g63`, `urus`, `ferrari296`, `cullinan`, `mclaren765`, `phantom`,
`revuelto`, `senna`, `laferrari`, `huayra`, `chiron`, `jesko`, `divo`,
`centodieci`.

**Automatic import (all cars at once):** put `CarImporter.lua` in
ServerStorage as a **ModuleScript** named `CarImporter`, then - NOT
during Play - run this in the Command Bar (the "Execute a command" line
at the bottom of Studio):

    require(game.ServerStorage.CarImporter)()

It searches the free models for every car, keeps the first good match
per car (name matches, sane part count), deletes every script inside it
(free models are a common way backdoor scripts sneak into games), and
drops it into `CarModels` with the right id. Output lists what it
picked and which cars need a manual pick. Then **save the place**.
Didn't like a pick? `require(game.ServerStorage.CarImporter)({ only =
{ "chiron" }, replace = true, skip = 1 })` takes the next match.

Toolbox models vary a lot in quality - pick ones with good ratings and
a sensible part count (a few hundred parts per car at most, or the game
lags with many cars). You can also import your own .fbx/.obj/.glb files
(File -> Import 3D), as long as their license allows it.

**Saving** (cash + owned cars) uses DataStores. To test it in Studio:
Game Settings -> Security -> turn on "Enable Studio Access to API
Services". Without that the game still works, it just won't save.

**Before publishing publicly:** set `USE_REAL_NAMES = false` at the top
of `CarSpawner.server.lua` - real car brand names can get a public
Roblox game taken down for trademark reasons. Economy tuning (starting
cash, cash per stud, speed scale) is at the top of the same file.

**Remove the template's old car spawner** so you don't have two
"Spawn Car" buttons - find the script behind its button (probably in
StarterGui or StarterPlayerScripts, near the "Admin Panel") and delete
or disable it.

# Tirana in Roblox

A hand-built road network of central Tirana and its surrounding
districts, for a Roblox driving game - real street names and real
relative geography, laid out from general knowledge of the city rather
than pulled from a live mapping API (this dev environment has no
outbound access to OpenStreetMap/Google Maps/etc. - see the note in
the top of `TiranaRoads.server.lua`). Treat the layout as "recognizable and
correctly arranged," not survey-precise coordinates.

## Babrru - the exact real map (recommended)

`BabrruMap.server.lua` / `BabrruMap.rbxmx` build **Babrru only**, from
real OpenStreetMap data: all 781 roads with their real names and
surfaces (asphalt, concrete, dirt, paths), all 2,651 buildings with
their real outlines, the 79 real zebra crossings, stop signs, traffic
lights, bus stops, the Tirana river and water, woods, street lamps,
blue street-name signs, and floating name labels for real places
(shops, schools, the church, the health centre, fuel stations). Scale:
2.5 studs = 1 real meter.

Setup: in the Explorer, right-click **ServerScriptService** ->
**Insert from File...** -> pick `tirana-roblox/BabrruMap.rbxmx`. That's
it - no copy/paste. Delete the old `TiranaRoads` script (the two maps
would overlap) and the default `Baseplate`. Press Play; it builds in a
few seconds and you spawn on a real Babrru street.

Buildings use their real floors, wall colour and roof shape wherever
OpenStreetMap has them (`building:levels`, `building:colour`,
`roof:shape`, `roof:colour`); elsewhere about half the small houses get
a pitched red-tile roof, as is common in Babrru. Specific buildings can
be corrected in `data/babrru_overrides.json` (keyed by OSM way id), e.g.
from satellite or Street View screenshots.

To rebuild it from a newer or bigger OpenStreetMap export:

    python tools/osm_to_babrru.py data/babrru.osm BabrruMap.server.lua

Map data (c) OpenStreetMap contributors, ODbL - the game shows this
credit on a sign next to the spawn point, which the license requires.

## What's here

- **`TiranaRoads.server.lua`** - ONE Script: the road data (every road
  and landmark, at the top of the file - edit it there) plus the code
  that builds it - a Part per road piece, a glowing pillar + name label
  per landmark, and grass ground under the whole map.

## Covers

Central Tirana (Skanderbeg Square, the boulevard, Blloku, Mother Teresa
Square, the Grand Park) plus roads out to **Babrru**, **Kamëz**,
**Laprakë**, **Kashar**, **Kombinat** and **Sauk**. Those six districts
sit at their real positions (converted from their published
latitude/longitude); the roads to them follow the right direction with
approximate curves, and Babrru's street grid is a stand-in rather than
its real street plan. The map is about 10 x 9 km at 1 stud = 1 meter.

## Setup (in Roblox Studio, on your PC)

1. In the Explorer, click **ServerScriptService** once.
2. Home tab -> the arrow under **Script** -> **Script**. Name it
   `TiranaRoads`, open it, delete what's in it, paste in everything from
   `TiranaRoads.server.lua`.
3. Press **Play**. Output shows `[TiranaRoads] Built ...` and the roads,
   landmarks and ground appear.

What it builds: dark asphalt roads with lane markings (a double center
line on the boulevard, dashed elsewhere), sidewalks, zebra crossings at
intersections, street lights, trees and bushes, city buildings along the
streets (taller toward the center, tall towers get neon edges and a red
beacon) and small houses in the suburbs - plus night lighting with glow.
Switches at the top of the builder part of the file (`NIGHT_MODE`,
`BUILDINGS`, `TREES`) turn pieces off if it lags. For the best-looking
lights, set **Lighting -> Technology** to **Future** in Studio.

The roads only exist while the game is running - they're built fresh on
every Play and vanish when you press Stop. That's normal: the script is
what's saved, and it rebuilds everything each time.

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
- While driving, **V** switches to the inside (driver's seat) view and back.
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

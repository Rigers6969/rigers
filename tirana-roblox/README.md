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

Four files, each goes in a specific place:

| File | What to insert | Where |
|---|---|---|
| `CarBuilder.lua` | **ModuleScript** named `CarBuilder` | ServerScriptService |
| `CarSpawner.server.lua` | **Script** (any name) | ServerScriptService |
| `SpawnCarButton.client.lua` | **LocalScript** (any name) | StarterPlayer > StarterPlayerScripts |

Then press Play:
- Click **Spawn Car (C)** (top right) or press **C** - a car appears
  next to you, facing the way you're looking.
- Walk up to it and press **E** ("Drive").
- **W/S** gas/brake/reverse, **A/D** steer, **Space** to get out.

The car is built from parts (painted body, tinted cabin, sloped
windshield, headlights, taillights, wheels with rims) and drives
arcade-style: smooth, can't flip over, doesn't get stuck. Tuning
numbers (top speed, acceleration, turning) are at the top of
`CarSpawner.server.lua`.

**Remove the template's old car spawner** so you don't have two
"Spawn Car" buttons - find the script behind its button (probably in
StarterGui or StarterPlayerScripts, near the "Admin Panel") and delete
or disable it.

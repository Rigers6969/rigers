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

## Adding cars

This repo intentionally doesn't include a custom car physics script -
**A-Chassis** (free, on the Roblox library/Toolbox) is the standard,
battle-tested framework most Roblox driving games are built on, and
duplicating that work here would just be a worse version of something
that already exists and works well. The plan:
1. In Studio's Toolbox, search "A-Chassis" and insert it.
2. Search "car" in the Toolbox for free body meshes to attach to it.
3. Roads sit with their top surface at **y = 0.5** (see
   `RoadBuilder.server.lua`'s `toVector3` comment) - spawn cars a
   little above that so they drop onto the road instead of clipping
   through it.

Want me to also build a simple traffic-AI script next (NPC cars that
follow `RoadData.lua`'s same waypoints)? That's a separate, addable
piece once real cars are in the scene.

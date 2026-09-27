--[[
	TiranaRoads - ONE Script in ServerScriptService. Builds every road,
	landmark marker and the grass ground each time the game starts - no
	separate RoadData ModuleScript needed anymore; the road data is at
	the top of this file (edit it here).

	Everything this builds exists only while the game runs: it's rebuilt
	on every Play and disappears when you press Stop. That's normal.
]]

-- Road data --------------------------------------------------------
-- 	Central Tirana's real street layout: real street names and landmarks, placed in their correct
-- 	relative geographic arrangement, but hand-authored from general
-- 	knowledge of the city rather than pulled from a live mapping API
-- 	(this dev sandbox has no outbound access to OpenStreetMap/Overpass -
-- 	see the repo's README). Treat this as "recognizable layout", not
-- 	survey-precise coordinates.
--
-- 	The outer districts (Babrru, Kamëz, Laprakë, Kashar, Kombinat, Sauk)
-- 	ARE at their real positions: converted from their published
-- 	latitude/longitude relative to Skanderbeg Square (41.3275 N,
-- 	19.8187 E). The roads leading to them follow the right corridor but
-- 	their exact curves are approximate, and each district's small street
-- 	grid is a stand-in, not its real streets.
--
-- 	Scale: 1 stud = 1 meter (a common convention for Roblox driving
-- 	games - keeps car/building sizes sane without extra scaling math).
-- 	Axes: +X = East, -X = West, +Z = South, -Z = North. Skanderbeg
-- 	Square (the real city center) sits at the origin, (0, 0).
--
-- 	Each road is a polyline through `points` ({x, z} pairs, in studs).
-- 	The builder below turns each consecutive pair of points into
-- 	one flat Part. `width` is in studs. Roads that should connect for
-- 	traffic AI share an exact endpoint coordinate with another road.
local RoadData = {
	Roads = {
		{
			name = "Bulevardi Dëshmorët e Kombit",
			description = "The city's main north-south boulevard, running through Skanderbeg Square.",
			type = "boulevard",
			width = 24,
			points = { {0, -650}, {0, 0}, {0, 700}, {0, 1400} },
		},
		{
			name = "Rruga e Kavajës",
			description = "Major artery heading west-southwest out of the center to Kombinat (real position). The outer curve is approximate.",
			type = "primary",
			width = 16,
			points = { {-50, 50}, {-700, 150}, {-1500, 250}, {-3000, 900}, {-4327, 1484} },
		},
		{
			name = "Rruga e Durrësit",
			description = "Major artery heading northwest past Laprakë, becoming the Tirana-Durrës road out to Kashar (both at real positions). The outer curve is approximate.",
			type = "primary",
			width = 16,
			points = { {-50, -100}, {-700, -600}, {-1400, -1100}, {-2028, -1329}, {-4200, -1850}, {-8436, -2319} },
		},
		{
			name = "Rruga e Elbasanit",
			description = "Major artery heading southeast out of the center towards Sauk (real position) and Elbasan. The outer curve is approximate.",
			type = "primary",
			width = 16,
			points = { {50, 100}, {700, 500}, {1400, 950}, {1350, 2000}, {1195, 3061} },
		},
		{
			name = "Rruga për Babrru",
			description = "North from the old train station area to Babrru (real position, ~3.4 km north of Skanderbeg Square). Right direction, approximate curve.",
			type = "primary",
			width = 14,
			points = { {0, -650}, {250, -1800}, {712, -3308} },
		},
		{
			name = "Rruga Babrru - Kamëz",
			description = "Northwest from Babrru to Kamëz (real position). Right direction, approximate curve.",
			type = "primary",
			width = 14,
			points = { {712, -3308}, {-1500, -4800}, {-4322, -6178} },
		},
		{
			name = "Babrru - Rruga 1 (E-W)",
			description = "Babrru neighborhood street - a stand-in grid around Babrru's real center, not its real street plan.",
			type = "local",
			width = 8,
			points = { {562, -3458}, {712, -3458}, {862, -3458} },
		},
		{
			name = "Babrru - Rruga 2 (E-W)",
			description = "Babrru neighborhood street - a stand-in grid around Babrru's real center, not its real street plan.",
			type = "local",
			width = 8,
			points = { {562, -3308}, {712, -3308}, {862, -3308} },
		},
		{
			name = "Babrru - Rruga 3 (E-W)",
			description = "Babrru neighborhood street - a stand-in grid around Babrru's real center, not its real street plan.",
			type = "local",
			width = 8,
			points = { {562, -3158}, {712, -3158}, {862, -3158} },
		},
		{
			name = "Babrru - Rruga 4 (N-S)",
			description = "Babrru neighborhood street - a stand-in grid around Babrru's real center, not its real street plan.",
			type = "local",
			width = 8,
			points = { {562, -3458}, {562, -3308}, {562, -3158} },
		},
		{
			name = "Babrru - Rruga 5 (N-S)",
			description = "Babrru neighborhood street - a stand-in grid around Babrru's real center, not its real street plan.",
			type = "local",
			width = 8,
			points = { {712, -3458}, {712, -3308}, {712, -3158} },
		},
		{
			name = "Babrru - Rruga 6 (N-S)",
			description = "Babrru neighborhood street - a stand-in grid around Babrru's real center, not its real street plan.",
			type = "local",
			width = 8,
			points = { {862, -3458}, {862, -3308}, {862, -3158} },
		},
		{
			name = "Rruga e Barrikadave",
			description = "Secondary street roughly parallel to the boulevard, connecting Kavajës to the Mother Teresa Square area. Both ends share an exact point with Kavajës / the boulevard so the network is actually connected.",
			type = "secondary",
			width = 10,
			points = { {-50, 50}, {-350, 450}, {0, 700} },
		},
		{
			name = "Blloku Connector",
			description = "Short link from Rruga e Barrikadave into the Blloku grid, so the grid isn't an isolated island for traffic AI.",
			type = "local",
			width = 7,
			points = { {-350, 450}, {-300, 500} },
		},
		{
			name = "Rruga e Kavajës - Blloku Nord",
			description = "Blloku district local street (north edge of the grid).",
			type = "local",
			width = 7,
			points = { {-300, 500}, {-100, 500} },
		},
		{
			name = "Rruga e Kavajës - Blloku Sud",
			description = "Blloku district local street (south edge of the grid).",
			type = "local",
			width = 7,
			points = { {-300, 650}, {-100, 650} },
		},
		{
			name = "Rruga Ibrahim Rugova",
			description = "Blloku district local street (west edge of the grid).",
			type = "local",
			width = 7,
			points = { {-300, 500}, {-300, 650} },
		},
		{
			name = "Rruga Sami Frashëri",
			description = "Blloku district local street (east edge of the grid).",
			type = "local",
			width = 7,
			points = { {-100, 500}, {-100, 650} },
		},
		{
			name = "Unaza (Ring Road) - West Connector",
			description = "Simplified peripheral loop for traffic AI to circulate on - schematic, not a survey-accurate trace of the real Unaza.",
			type = "ring",
			width = 14,
			points = { {-1400, -1100}, {-1500, 250} },
		},
		{
			name = "Unaza (Ring Road) - South Connector",
			description = "Simplified peripheral loop for traffic AI to circulate on - schematic, not a survey-accurate trace of the real Unaza.",
			type = "ring",
			width = 14,
			points = { {-1500, 250}, {0, 1400} },
		},
		{
			name = "Unaza (Ring Road) - Southeast Connector",
			description = "Simplified peripheral loop for traffic AI to circulate on - schematic, not a survey-accurate trace of the real Unaza.",
			type = "ring",
			width = 14,
			points = { {0, 1400}, {1400, 950} },
		},
		{
			name = "Unaza (Ring Road) - North Connector",
			description = "Simplified peripheral loop for traffic AI to circulate on - schematic, not a survey-accurate trace of the real Unaza.",
			type = "ring",
			width = 14,
			points = { {1400, 950}, {-1400, -1100} },
		},
	},

	-- Road width (studs) by type, matched to real relative proportions
	-- (a boulevard is wider than a residential street) rather than
	-- exact real measurements.
	RoadTypeColors = {
		boulevard = Color3.fromRGB(90, 90, 95),
		primary = Color3.fromRGB(80, 80, 85),
		secondary = Color3.fromRGB(75, 75, 80),
		local_ = Color3.fromRGB(70, 70, 75), -- "local" is a Lua keyword-adjacent name to avoid confusion; the builder maps type "local" to this
		ring = Color3.fromRGB(85, 85, 90),
	},

	Landmarks = {
		{ name = "Sheshi Skënderbej (Skanderbeg Square)", position = {0, 0} },
		{ name = "Sheshi Nënë Tereza (Mother Teresa Square)", position = {0, 700} },
		{ name = "Parku i Madh / Liqeni Artificial (Grand Park & Artificial Lake)", position = {0, 1400} },
		{ name = "Blloku", position = {-200, 575} },
		{ name = "Ish-Stacioni i Trenit (Old Train Station area)", position = {0, -650} },
		-- Outer districts at their real positions (converted from their
		-- published latitude/longitude - see the module docstring).
		{ name = "Babrru", position = {712, -3308} },
		{ name = "Kamëz", position = {-4322, -6178} },
		{ name = "Laprakë", position = {-2028, -1329} },
		{ name = "Kashar", position = {-8436, -2319} },
		{ name = "Kombinat", position = {-4327, 1484} },
		{ name = "Sauk", position = {1195, 3061} },
	},
}

local Workspace = game:GetService("Workspace")

local function clearFolder(name)
	local existing = Workspace:FindFirstChild(name)
	if existing then
		existing:Destroy()
	end
	local folder = Instance.new("Folder")
	folder.Name = name
	folder.Parent = Workspace
	return folder
end

local roadsFolder = clearFolder("Roads")
local landmarksFolder = clearFolder("Landmarks")

local function toVector3(point)
	-- RoadData points are {x, z}; roads sit flat on the ground at y = 0,
	-- with the part's top surface at y = 0.5 (part center at y = 0,
	-- thickness 1) so a car's wheels rest right at y ~= 0.5 + wheel radius.
	return Vector3.new(point[1], 0, point[2])
end

local function colorForType(roadType)
	local key = roadType == "local" and "local_" or roadType
	return (RoadData.RoadTypeColors and RoadData.RoadTypeColors[key]) or Color3.fromRGB(80, 80, 80)
end

local function buildSegment(road, startPoint, endPoint)
	local a = toVector3(startPoint)
	local b = toVector3(endPoint)
	local length = (b - a).Magnitude
	if length < 0.01 then
		return -- skip degenerate zero-length segments
	end

	local midpoint = a:Lerp(b, 0.5)
	local part = Instance.new("Part")
	part.Name = road.name
	part.Anchored = true
	part.CanCollide = true
	part.Material = Enum.Material.Asphalt
	part.Color = colorForType(road.type)
	part.Size = Vector3.new(road.width, 1, length)
	-- CFrame.lookAt orients the part's local Z axis along the a->b
	-- direction, which is exactly what's needed for Size.Z (length) to
	-- span the segment - which way is "front" vs "back" doesn't matter
	-- for a symmetric flat road slab.
	part.CFrame = CFrame.lookAt(midpoint, b)
	part.Parent = roadsFolder
end

-- Roblox caps a Part at 2048 studs on any side, so a longer stretch would
-- silently come out too short - long stretches are built in pieces.
local MAX_PIECE = 1000

for _, road in ipairs(RoadData.Roads) do
	for i = 1, #road.points - 1 do
		local a, b = road.points[i], road.points[i + 1]
		local dx, dz = b[1] - a[1], b[2] - a[2]
		local pieces = math.max(1, math.ceil(math.sqrt(dx * dx + dz * dz) / MAX_PIECE))
		for k = 1, pieces do
			local t0, t1 = (k - 1) / pieces, k / pieces
			buildSegment(road, { a[1] + dx * t0, a[2] + dz * t0 }, { a[1] + dx * t1, a[2] + dz * t1 })
		end
	end
end

for _, landmark in ipairs(RoadData.Landmarks) do
	local pos = toVector3(landmark.position)

	-- A simple square glowing pillar, not a Cylinder shape - avoids
	-- having to reason about which local axis a cylinder's round faces
	-- point along, and looks the same as a landmark marker either way.
	local marker = Instance.new("Part")
	marker.Name = landmark.name
	marker.Anchored = true
	marker.CanCollide = false
	marker.Size = Vector3.new(4, 20, 4)
	marker.CFrame = CFrame.new(pos + Vector3.new(0, 10, 0))
	marker.Material = Enum.Material.Neon
	marker.Color = Color3.fromRGB(201, 162, 75) -- matches the Wayne Factory gold accent, purely cosmetic
	marker.Transparency = 0.7
	marker.Parent = landmarksFolder

	local billboard = Instance.new("BillboardGui")
	billboard.Name = "Label"
	billboard.Size = UDim2.new(0, 220, 0, 40)
	billboard.StudsOffset = Vector3.new(0, 14, 0)
	billboard.AlwaysOnTop = true
	billboard.Parent = marker

	local label = Instance.new("TextLabel")
	label.Size = UDim2.fromScale(1, 1)
	label.BackgroundTransparency = 1
	label.TextColor3 = Color3.fromRGB(255, 255, 255)
	label.TextStrokeTransparency = 0
	label.Font = Enum.Font.GothamBold
	label.TextSize = 18
	label.Text = landmark.name
	label.Parent = billboard
end

-- Grass ground under the whole map, tiled because a single Part can't be
-- bigger than 2048 studs. Covers every road and landmark plus a margin.
local groundFolder = clearFolder("TiranaGround")
local minX, maxX, minZ, maxZ = math.huge, -math.huge, math.huge, -math.huge
local function include(point)
	minX, maxX = math.min(minX, point[1]), math.max(maxX, point[1])
	minZ, maxZ = math.min(minZ, point[2]), math.max(maxZ, point[2])
end
for _, road in ipairs(RoadData.Roads) do
	for _, point in ipairs(road.points) do
		include(point)
	end
end
for _, landmark in ipairs(RoadData.Landmarks) do
	include(landmark.position)
end

local TILE = 2000
local MARGIN = 400
minX, maxX, minZ, maxZ = minX - MARGIN, maxX + MARGIN, minZ - MARGIN, maxZ + MARGIN
local tilesX = math.ceil((maxX - minX) / TILE)
local tilesZ = math.ceil((maxZ - minZ) / TILE)
for ix = 0, tilesX - 1 do
	for iz = 0, tilesZ - 1 do
		local tile = Instance.new("Part")
		tile.Name = "Ground"
		tile.Anchored = true
		tile.CanCollide = true
		tile.Material = Enum.Material.Grass
		tile.Color = Color3.fromRGB(96, 120, 74)
		tile.Size = Vector3.new(TILE, 1, TILE)
		tile.CFrame = CFrame.new(minX + (ix + 0.5) * TILE, -1, minZ + (iz + 0.5) * TILE)
		tile.Parent = groundFolder
	end
end

print(("[TiranaRoads] Built %d road segments and %d landmarks."):format(#roadsFolder:GetChildren(), #landmarksFolder:GetChildren()))

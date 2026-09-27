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

local Lighting = game:GetService("Lighting")
local Workspace = game:GetService("Workspace")

-- Look settings - flip any of these off if the game gets laggy.
local NIGHT_MODE = true -- night sky, glow, and street lamps that light the road
local BUILDINGS = true -- city buildings along the roads (houses further out)
local TREES = true -- trees and bushes along the roads
local CITY_RADIUS = 2200 -- inside this distance from Skanderbeg Square: city blocks; outside: houses

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
local markingsFolder = clearFolder("RoadMarkings")
local sidewalksFolder = clearFolder("Sidewalks")
local lightsFolder = clearFolder("StreetLights")
local landmarksFolder = clearFolder("Landmarks")

-- Roads are 1 stud thick with their top at y = 0.5; sidewalks are flush
-- with them (so cars never catch on a curb), markings sit just on top.
local ROAD_TOP = 0.5
local MARK_Y = ROAD_TOP + 0.03
local ASPHALT = Color3.fromRGB(52, 52, 56)
local LINE_WHITE = Color3.fromRGB(235, 235, 230)
local SIDEWALK_COLOR = Color3.fromRGB(168, 166, 160)
local POLE_COLOR = Color3.fromRGB(60, 62, 68)
local LAMP_COLOR = Color3.fromRGB(255, 226, 160)

-- Roblox caps a Part at 2048 studs on any side, so a longer stretch would
-- silently come out too short - long strips are built in pieces.
local MAX_PIECE = 1000
local DASH, GAP = 3, 9
local LIGHT_SPACING = 45

local STYLE = {
	boulevard = { sidewalk = 5, center = "double", edges = true, lights = true, crosswalk = true },
	primary = { sidewalk = 3.5, center = "dashed", edges = true, lights = true, crosswalk = true },
	ring = { sidewalk = 3, center = "dashed", edges = true, lights = true, crosswalk = false },
	secondary = { sidewalk = 3, center = "dashed", edges = false, lights = false, crosswalk = true },
	["local"] = { sidewalk = 2.5, center = nil, edges = false, lights = false, crosswalk = false },
}

local built = 0
local function newPart(parent, name, size, cframe, color, material, collide)
	local p = Instance.new("Part")
	p.Name = name
	p.Anchored = true
	p.Size = size
	p.CFrame = cframe
	p.Color = color
	p.Material = material
	p.CanCollide = collide
	if not collide then
		p.CanQuery = false
		p.CanTouch = false
		p.CastShadow = false
	end
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	p.Parent = parent
	built = built + 1
	-- Yield now and then so building thousands of parts never trips
	-- Roblox's "script ran too long" limit.
	if built % 500 == 0 then
		task.wait()
	end
	return p
end

local function toVector3(point)
	return Vector3.new(point[1], 0, point[2])
end

-- A flat strip running from distance d0 to d1 along the a->b line,
-- shifted sideways by `lateral` (positive = right of the a->b direction).
local function strip(parent, name, a, b, d0, d1, lateral, width, yCenter, thickness, color, material, collide)
	local dir = b - a
	local len = dir.Magnitude
	if len < 0.01 or d1 - d0 < 0.05 then
		return
	end
	local unit = dir / len
	local right = Vector3.new(-unit.Z, 0, unit.X)
	local pieces = math.max(1, math.ceil((d1 - d0) / MAX_PIECE))
	for k = 1, pieces do
		local s0 = d0 + (d1 - d0) * (k - 1) / pieces
		local s1 = d0 + (d1 - d0) * k / pieces
		local mid = a + unit * ((s0 + s1) / 2) + right * lateral
		local center = Vector3.new(mid.X, yCenter, mid.Z)
		-- lookAt points the part's length (Z) along the road; its X axis is
		-- then the road's sideways direction.
		newPart(parent, name, Vector3.new(width, thickness, s1 - s0), CFrame.lookAt(center, center + unit), color, material, collide)
	end
end

-- Where 2+ roads share a point is an intersection: sidewalks, lines and
-- lights stop short of it by enough to clear the widest road there.
local function pointKey(point)
	return point[1] .. "," .. point[2]
end
local roadsAtPoint, widestAtPoint = {}, {}
for _, road in ipairs(RoadData.Roads) do
	local seen = {}
	for _, point in ipairs(road.points) do
		local k = pointKey(point)
		if not seen[k] then
			seen[k] = true
			roadsAtPoint[k] = (roadsAtPoint[k] or 0) + 1
			widestAtPoint[k] = math.max(widestAtPoint[k] or 0, road.width)
		end
	end
end
local function clearanceAt(point)
	local k = pointKey(point)
	if (roadsAtPoint[k] or 0) < 2 then
		return 0
	end
	return widestAtPoint[k] / 2 + 6
end

local function buildCrosswalk(a, b, at, width)
	local stripe, spacing = 0.8, 1.6
	local lateral = -width / 2 + 1.2
	while lateral <= width / 2 - 1.2 do
		strip(markingsFolder, "Crosswalk", a, b, at, at + 3, lateral, stripe, MARK_Y, 0.05, LINE_WHITE, Enum.Material.SmoothPlastic, false)
		lateral = lateral + spacing
	end
end

local lampCount = 0
local function buildStreetLight(a, b, at, side, road, style)
	local dir = (b - a).Unit
	local right = Vector3.new(-dir.Z, 0, dir.X)
	local poleOffset = side * (road.width / 2 + style.sidewalk - 0.6)
	local base = a + dir * at
	local function place(lateral, y)
		local pos = base + right * lateral
		local center = Vector3.new(pos.X, y, pos.Z)
		return CFrame.lookAt(center, center + dir)
	end
	newPart(lightsFolder, "Pole", Vector3.new(0.5, 12, 0.5), place(poleOffset, ROAD_TOP + 6), POLE_COLOR, Enum.Material.Metal, true)
	-- The arm reaches from the pole back over the road (toward the center).
	newPart(lightsFolder, "Arm", Vector3.new(3, 0.3, 0.3), place(poleOffset - side * 1.5, ROAD_TOP + 12), POLE_COLOR, Enum.Material.Metal, false)
	local lamp = newPart(lightsFolder, "Lamp", Vector3.new(1.4, 0.35, 0.8), place(poleOffset - side * 3, ROAD_TOP + 11.8), LAMP_COLOR, Enum.Material.Neon, false)
	lampCount = lampCount + 1
	-- Every second lamp casts real light: looks the same at night for half the GPU cost.
	if NIGHT_MODE and lampCount % 2 == 0 then
		local light = Instance.new("SpotLight")
		light.Face = Enum.NormalId.Bottom
		light.Range = 28
		light.Angle = 120
		light.Brightness = 2.5
		light.Color = LAMP_COLOR
		light.Shadows = false
		light.Parent = lamp
	end
end

local function buildRoadSegment(road, pa, pb)
	local style = STYLE[road.type] or STYLE["local"]
	local a, b = toVector3(pa), toVector3(pb)
	local len = (b - a).Magnitude
	if len < 0.01 then
		return
	end
	local w = road.width

	strip(roadsFolder, road.name, a, b, 0, len, 0, w, 0, 1, ASPHALT, Enum.Material.Asphalt, true)

	local startClear, endClear = clearanceAt(pa), clearanceAt(pb)
	local t0, t1 = startClear, len - endClear
	if t1 - t0 < 8 then
		return -- too short between intersections for sidewalks/markings
	end

	local sw = style.sidewalk
	for _, side in ipairs({ -1, 1 }) do
		strip(sidewalksFolder, "Sidewalk", a, b, t0, t1, side * (w / 2 + sw / 2), sw, 0, 1, SIDEWALK_COLOR, Enum.Material.Concrete, true)
		if style.edges then
			strip(markingsFolder, "EdgeLine", a, b, t0, t1, side * (w / 2 - 0.7), 0.3, MARK_Y, 0.05, LINE_WHITE, Enum.Material.SmoothPlastic, false)
		end
	end

	local lineStart, lineEnd = t0, t1
	if style.crosswalk then
		if startClear > 0 then
			buildCrosswalk(a, b, t0 + 1, w)
			lineStart = t0 + 6
		end
		if endClear > 0 then
			buildCrosswalk(a, b, t1 - 4, w)
			lineEnd = t1 - 6
		end
	end

	if style.center == "double" then
		for _, lateral in ipairs({ -0.35, 0.35 }) do
			strip(markingsFolder, "CenterLine", a, b, lineStart, lineEnd, lateral, 0.25, MARK_Y, 0.05, LINE_WHITE, Enum.Material.SmoothPlastic, false)
		end
	elseif style.center == "dashed" then
		local d = lineStart + GAP / 2
		while d + DASH <= lineEnd do
			strip(markingsFolder, "CenterDash", a, b, d, d + DASH, 0, 0.3, MARK_Y, 0.05, LINE_WHITE, Enum.Material.SmoothPlastic, false)
			d = d + DASH + GAP
		end
	end

	if style.lights then
		local side = 1
		local d = t0 + 10
		while d < t1 - 5 do
			buildStreetLight(a, b, d, side, road, style)
			side = -side
			d = d + LIGHT_SPACING
		end
	end
end

for _, road in ipairs(RoadData.Roads) do
	for i = 1, #road.points - 1 do
		buildRoadSegment(road, road.points[i], road.points[i + 1])
	end
end

---------------------------------------------------------------------
-- Roadside: trees, bushes, city buildings, suburban houses
---------------------------------------------------------------------

local treesFolder = clearFolder("Trees")
local buildingsFolder = clearFolder("Buildings")
local rng = Random.new(2026) -- fixed seed: the city looks the same every time

local FACADES = {
	Color3.fromRGB(232, 93, 74), Color3.fromRGB(245, 178, 66), Color3.fromRGB(111, 176, 214),
	Color3.fromRGB(142, 202, 128), Color3.fromRGB(206, 120, 186), Color3.fromRGB(240, 132, 58),
	Color3.fromRGB(236, 228, 210), Color3.fromRGB(190, 190, 185),
}
local GLASS = { Color3.fromRGB(40, 60, 90), Color3.fromRGB(30, 45, 60), Color3.fromRGB(60, 85, 100) }
local NEON_TRIMS = { Color3.fromRGB(255, 40, 220), Color3.fromRGB(40, 220, 255), Color3.fromRGB(255, 200, 60) }
local WINDOW_LIT = Color3.fromRGB(255, 214, 140)
local WINDOW_DARK = Color3.fromRGB(30, 38, 52)
local GROUND_TOP = -0.5 -- top of the grass

local function pick(list)
	return list[rng:NextInteger(1, #list)]
end

-- Every road segment, for keeping buildings off the roads.
local segments = {}
for _, road in ipairs(RoadData.Roads) do
	local style = STYLE[road.type] or STYLE["local"]
	for i = 1, #road.points - 1 do
		table.insert(segments, {
			a = toVector3(road.points[i]),
			b = toVector3(road.points[i + 1]),
			reach = road.width / 2 + style.sidewalk,
		})
	end
end

local function distanceToSegment(p, a, b)
	local ab = b - a
	local lengthSq = ab.X * ab.X + ab.Z * ab.Z
	local t = 0
	if lengthSq > 0 then
		t = math.clamp(((p.X - a.X) * ab.X + (p.Z - a.Z) * ab.Z) / lengthSq, 0, 1)
	end
	local cx, cz = a.X + ab.X * t, a.Z + ab.Z * t
	return math.sqrt((p.X - cx) ^ 2 + (p.Z - cz) ^ 2)
end

local placed = {}
local function spotIsFree(pos, radius)
	for _, seg in ipairs(segments) do
		if distanceToSegment(pos, seg.a, seg.b) < seg.reach + radius then
			return false
		end
	end
	for _, other in ipairs(placed) do
		local dx, dz = pos.X - other.pos.X, pos.Z - other.pos.Z
		if dx * dx + dz * dz < (radius + other.radius) ^ 2 then
			return false
		end
	end
	return true
end

-- A part standing on the ground at `pos`, turned to face along `dir`.
local function standing(parent, name, size, pos, dir, color, material, collide)
	local center = Vector3.new(pos.X, GROUND_TOP + size.Y / 2, pos.Z)
	return newPart(parent, name, size, CFrame.lookAt(center, center + dir), color, material, collide)
end

local function buildTree(pos)
	local trunkH = rng:NextNumber(5, 8)
	local trunk = Vector3.new(pos.X, GROUND_TOP + trunkH / 2, pos.Z)
	newPart(treesFolder, "Trunk", Vector3.new(0.8, trunkH, 0.8), CFrame.new(trunk), Color3.fromRGB(95, 70, 50), Enum.Material.Wood, true)
	local size = rng:NextNumber(7, 11)
	local leaves = newPart(treesFolder, "Leaves", Vector3.new(size, size, size),
		CFrame.new(pos.X, GROUND_TOP + trunkH + size * 0.3, pos.Z), Color3.fromRGB(45, 110 + rng:NextInteger(0, 40), 45), Enum.Material.LeafyGrass, false)
	leaves.Shape = Enum.PartType.Ball
end

local function buildBush(pos)
	local size = rng:NextNumber(3, 5)
	local bush = newPart(treesFolder, "Bush", Vector3.new(size, size, size),
		CFrame.new(pos.X, GROUND_TOP + size * 0.35, pos.Z), Color3.fromRGB(50, 120 + rng:NextInteger(0, 30), 50), Enum.Material.LeafyGrass, false)
	bush.Shape = Enum.PartType.Ball
end

local function buildCityBuilding(pos, dir, right, side, along, depth, centerDistance)
	local closeness = 1 - math.clamp(centerDistance / CITY_RADIUS, 0, 1)
	local h = rng:NextNumber(12, 24) + closeness * closeness * rng:NextNumber(10, 110)
	local model = Instance.new("Model")
	model.Name = "Building"
	model.Parent = buildingsFolder

	local glassTower = h > 45 and rng:NextNumber() < 0.5
	local bodyColor = glassTower and pick(GLASS) or pick(FACADES)
	local body = standing(model, "Body", Vector3.new(depth, h, along), pos, dir, bodyColor, glassTower and Enum.Material.Glass or Enum.Material.Concrete, true)
	if glassTower then
		body.Reflectance = 0.2
	end

	-- Window bands: lit and glowing at night, dark glass by day.
	local step = math.max(8, h / 8)
	local y = 5
	while y < h - 3 do
		local lit = NIGHT_MODE and rng:NextNumber() < 0.7
		local band = newPart(model, "Windows", Vector3.new(depth + 0.3, 2.2, along + 0.3),
			CFrame.lookAt(Vector3.new(pos.X, GROUND_TOP + y, pos.Z), Vector3.new(pos.X, GROUND_TOP + y, pos.Z) + dir),
			lit and WINDOW_LIT or WINDOW_DARK, lit and Enum.Material.Neon or Enum.Material.Glass, false)
		if lit then
			band.Transparency = 0.35
		end
		y = y + step
	end

	local top = GROUND_TOP + h
	newPart(model, "Roof", Vector3.new(depth + 0.6, 0.6, along + 0.6), CFrame.lookAt(Vector3.new(pos.X, top + 0.3, pos.Z), Vector3.new(pos.X, top + 0.3, pos.Z) + dir),
		Color3.fromRGB(80, 80, 86), Enum.Material.Concrete, true)

	-- Tall towers: neon edges on the street side and a red beacon on top.
	if h > 50 then
		local trim = pick(NEON_TRIMS)
		local face = pos - right * side * (depth / 2)
		for _, e in ipairs({ -1, 1 }) do
			local edge = face + dir * (e * along / 2)
			newPart(model, "NeonEdge", Vector3.new(0.5, h, 0.5), CFrame.new(edge.X, GROUND_TOP + h / 2, edge.Z), trim, Enum.Material.Neon, false)
		end
		local beacon = newPart(model, "Beacon", Vector3.new(1.6, 1.6, 1.6), CFrame.new(pos.X, top + 1.4, pos.Z), Color3.fromRGB(255, 40, 40), Enum.Material.Neon, false)
		beacon.Shape = Enum.PartType.Ball
	end
end

local function buildHouse(pos, dir, along, depth)
	local h = rng:NextNumber(6, 10)
	local model = Instance.new("Model")
	model.Name = "House"
	model.Parent = buildingsFolder
	standing(model, "Walls", Vector3.new(depth, h, along), pos, dir, pick(FACADES), Enum.Material.Concrete, true)
	local lit = NIGHT_MODE and rng:NextNumber() < 0.6
	newPart(model, "Windows", Vector3.new(depth + 0.2, 1.8, along + 0.2),
		CFrame.lookAt(Vector3.new(pos.X, GROUND_TOP + h * 0.55, pos.Z), Vector3.new(pos.X, GROUND_TOP + h * 0.55, pos.Z) + dir),
		lit and WINDOW_LIT or WINDOW_DARK, lit and Enum.Material.Neon or Enum.Material.Glass, false)
	newPart(model, "Roof", Vector3.new(depth + 1, 0.8, along + 1),
		CFrame.lookAt(Vector3.new(pos.X, GROUND_TOP + h + 0.4, pos.Z), Vector3.new(pos.X, GROUND_TOP + h + 0.4, pos.Z) + dir),
		Color3.fromRGB(170, 75, 55), Enum.Material.Slate, true)
end

local function dressSegment(road, pa, pb)
	local style = STYLE[road.type] or STYLE["local"]
	local a, b = toVector3(pa), toVector3(pb)
	local len = (b - a).Magnitude
	if len < 0.01 then
		return
	end
	local dir = (b - a) / len
	local right = Vector3.new(-dir.Z, 0, dir.X)
	local t0, t1 = clearanceAt(pa), len - clearanceAt(pb)
	local edge = road.width / 2 + style.sidewalk

	if TREES and road.type ~= "local" then
		local side = -1
		local d = t0 + 22 -- offset from the street lights
		while d < t1 - 5 do
			local pos = a + dir * d + right * (side * (edge + 3))
			if spotIsFree(pos, 1) then
				buildTree(pos)
			end
			local bushPos = a + dir * (d + 20) + right * (-side * (edge + 2.5))
			if d + 20 < t1 - 5 and spotIsFree(bushPos, 1) then
				buildBush(bushPos)
			end
			side = -side
			d = d + 40
		end
	end

	if BUILDINGS then
		local spacing = 34
		for _, side in ipairs({ -1, 1 }) do
			local d = t0 + spacing / 2
			while d < t1 - spacing / 2 do
				local along = rng:NextNumber(16, spacing - 6)
				local depth = rng:NextNumber(14, 24)
				local roadPoint = a + dir * d
				local centerDistance = roadPoint.Magnitude
				local inCity = centerDistance < CITY_RADIUS
				if not inCity then
					along, depth = rng:NextNumber(10, 14), rng:NextNumber(10, 14)
				end
				local pos = roadPoint + right * (side * (edge + 6 + depth / 2))
				local radius = math.max(along, depth) / 2 + 1
				-- Suburbs are sparser than the city.
				if (inCity or rng:NextNumber() < 0.55) and spotIsFree(pos, radius) then
					table.insert(placed, { pos = pos, radius = radius })
					if inCity then
						buildCityBuilding(pos, dir, right, side, along, depth, centerDistance)
					else
						buildHouse(pos, dir, along, depth)
					end
				end
				d = d + spacing
			end
		end
	end
end

for _, road in ipairs(RoadData.Roads) do
	for i = 1, #road.points - 1 do
		dressSegment(road, road.points[i], road.points[i + 1])
	end
end

---------------------------------------------------------------------
-- Night lighting
---------------------------------------------------------------------

if NIGHT_MODE then
	Lighting.ClockTime = 21
	Lighting.Brightness = 1
	Lighting.Ambient = Color3.fromRGB(40, 40, 55)
	Lighting.OutdoorAmbient = Color3.fromRGB(70, 70, 95)
	local bloom = Lighting:FindFirstChildOfClass("BloomEffect") or Instance.new("BloomEffect")
	bloom.Intensity = 0.9
	bloom.Size = 32
	bloom.Threshold = 0.85
	bloom.Parent = Lighting
	local color = Lighting:FindFirstChild("TiranaNightColor") or Instance.new("ColorCorrectionEffect")
	color.Name = "TiranaNightColor"
	color.Saturation = 0.15
	color.Contrast = 0.1
	color.Parent = Lighting
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
	-- Floats 8 studs up so cars drive underneath instead of through it.
	marker.CFrame = CFrame.new(pos + Vector3.new(0, 18, 0))
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

print(("[TiranaRoads] Built %d parts: roads, sidewalks, markings, crosswalks, street lights, trees, %d buildings and %d landmarks."):format(built, #buildingsFolder:GetChildren(), #landmarksFolder:GetChildren()))

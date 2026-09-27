--[[
	RoadBuilder.server.lua - run this ONCE (paste into ServerScriptService
	and hit Play, or paste into the Command Bar's "Run" via a temporary
	Script) to build every road and landmark marker from RoadData.lua.

	It's idempotent-ish: it clears any previously-built "Roads" and
	"Landmarks" folders first, so re-running it after editing
	RoadData.lua rebuilds cleanly instead of duplicating parts.
]]

-- RoadData.lua must be a sibling ModuleScript in the same folder as
-- this script (ServerScriptService, per the README's import steps).
local RoadData = require(script.Parent.RoadData)

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

print(("RoadBuilder: built %d road segments and %d landmarks."):format(#roadsFolder:GetChildren(), #landmarksFolder:GetChildren()))

--[[
	BuildingGenerator - drop-in replacement for the template's
	BuildingGenerator ModuleScript. Same API (BuildingGenerator.Generate(parent))
	and the same CityConfiguration keys, so whatever already calls it
	keeps working unchanged.

	What changed vs the template: every building used to have the exact
	same square footprint (only height/color varied), so the city looked
	like copy-pasted blocks. Now each lot gets one of five building types
	(Tirana-style painted apartment block, stepped tower, glass tower,
	ground-floor shop, small park), its own width/depth, a random nudge
	inside its lot, and taller buildings cluster toward the map center
	like a real downtown. Every building still stays inside the same lot
	the template gave it, so nothing new pokes into the roads.
]]

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Config = require(ReplicatedStorage:WaitForChild("CityConfiguration"))

local BuildingGenerator = {}

local function safeMaterial(name, fallback)
	local ok, material = pcall(function()
		return Enum.Material[name]
	end)
	if ok and material then
		return material
	end
	return fallback
end

local PLASTER = safeMaterial("Plaster", Enum.Material.Concrete)

-- Tirana's famous painted facades - bright, warm, varied.
local FACADE_COLORS = {
	Color3.fromRGB(232, 93, 74),
	Color3.fromRGB(245, 178, 66),
	Color3.fromRGB(111, 176, 214),
	Color3.fromRGB(142, 202, 128),
	Color3.fromRGB(206, 120, 186),
	Color3.fromRGB(240, 132, 58),
	Color3.fromRGB(236, 228, 210),
	Color3.fromRGB(190, 190, 185),
}
local GLASS_COLORS = {
	Color3.fromRGB(70, 110, 150),
	Color3.fromRGB(60, 90, 110),
	Color3.fromRGB(95, 130, 140),
	Color3.fromRGB(40, 55, 75),
}
local AWNING_COLORS = {
	Color3.fromRGB(200, 40, 40),
	Color3.fromRGB(30, 110, 60),
	Color3.fromRGB(30, 70, 150),
	Color3.fromRGB(230, 170, 30),
}
local TRIM_COLOR = Color3.fromRGB(235, 232, 225)
local WINDOW_COLOR = Color3.fromRGB(30, 38, 52)
local ROOF_COLOR = Color3.fromRGB(95, 95, 100)
local METAL_COLOR = Color3.fromRGB(160, 162, 168)

local function pick(rng, list)
	return list[rng:NextInteger(1, #list)]
end

local function lerp(a, b, t)
	return a + (b - a) * t
end

local function makePart(parent, name, size, position, color, material, collide)
	local p = Instance.new("Part")
	p.Name = name
	p.Anchored = true
	p.Size = size
	p.CFrame = CFrame.new(position)
	p.Color = color
	p.Material = material
	p.CanCollide = collide ~= false
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	p.Parent = parent
	return p
end

local function box(model, name, cx, baseY, cz, w, h, d, color, material)
	return makePart(model, name, Vector3.new(w, h, d), Vector3.new(cx, baseY + h / 2, cz), color, material)
end

-- Strip windows wrapping all four sides, one per floor.
local function addWindowBands(model, cx, baseY, cz, w, h, d, floorH)
	local y = baseY + floorH * 0.55
	while y < baseY + h - floorH * 0.4 do
		local band = makePart(model, "Windows", Vector3.new(w + 0.3, floorH * 0.4, d + 0.3),
			Vector3.new(cx, y, cz), WINDOW_COLOR, Enum.Material.Glass, false)
		band.Reflectance = 0.15
		y = y + floorH
	end
end

-- Balcony ledge wrapping the building every other floor.
local function addBalconies(model, cx, baseY, cz, w, h, d, floorH)
	local y = baseY + floorH * 2
	while y < baseY + h - floorH do
		makePart(model, "Balcony", Vector3.new(w + 1.4, 0.35, d + 1.4), Vector3.new(cx, y, cz), TRIM_COLOR, Enum.Material.Concrete, false)
		y = y + floorH * 2
	end
end

local function addRoof(model, rng, cx, topY, cz, w, d)
	makePart(model, "Roof", Vector3.new(w + 0.6, 0.6, d + 0.6), Vector3.new(cx, topY + 0.3, cz), ROOF_COLOR, Enum.Material.Concrete)
	if rng:NextNumber() < 0.6 and w > 8 and d > 8 then
		local ox = rng:NextNumber(-w / 4, w / 4)
		local oz = rng:NextNumber(-d / 4, d / 4)
		makePart(model, "ACUnit", Vector3.new(3, 2, 3), Vector3.new(cx + ox, topY + 1.6, cz + oz), METAL_COLOR, Enum.Material.Metal)
	end
	if rng:NextNumber() < 0.3 and w > 8 and d > 8 then
		local tank = makePart(model, "WaterTank", Vector3.new(4, 3, 3), Vector3.new(cx - w / 4, topY + 2.6, cz + d / 4), TRIM_COLOR, Enum.Material.SmoothPlastic)
		tank.Shape = Enum.PartType.Cylinder
		tank.CFrame = CFrame.new(tank.Position) * CFrame.Angles(0, 0, math.rad(90))
	end
end

local function buildApartment(model, rng, cx, cz, w, d, h, facades)
	local floorH = 7
	local color = pick(rng, facades)
	box(model, "Walls", cx, 0, cz, w, h, d, color, PLASTER)
	addWindowBands(model, cx, 0, cz, w, h, d, floorH)
	addBalconies(model, cx, 0, cz, w, h, d, floorH)
	addRoof(model, rng, cx, h, cz, w, d)
end

local function buildSteppedTower(model, rng, cx, cz, w, d, baseH, upperH, facades)
	local floorH = 7
	local baseColor = pick(rng, facades)
	box(model, "Base", cx, 0, cz, w, baseH, d, baseColor, PLASTER)
	addWindowBands(model, cx, 0, cz, w, baseH, d, floorH)
	makePart(model, "Setback", Vector3.new(w + 0.4, 0.6, d + 0.4), Vector3.new(cx, baseH + 0.3, cz), TRIM_COLOR, Enum.Material.Concrete)

	local uw, ud = w * 0.62, d * 0.62
	local upperColor = rng:NextNumber() < 0.5 and pick(rng, GLASS_COLORS) or TRIM_COLOR
	box(model, "Tower", cx, baseH, cz, uw, upperH, ud, upperColor, Enum.Material.Concrete)
	addWindowBands(model, cx, baseH, cz, uw, upperH, ud, 6)
	addRoof(model, rng, cx, baseH + upperH, cz, uw, ud)
end

local function buildGlassTower(model, rng, cx, cz, w, d, h)
	local glass = box(model, "GlassTower", cx, 0, cz, w, h, d, pick(rng, GLASS_COLORS), Enum.Material.Glass)
	glass.Reflectance = 0.25

	-- Vertical steel mullions at the corners and middle of each face.
	local halfW, halfD = w / 2, d / 2
	local posts = {
		{ halfW, halfD }, { -halfW, halfD }, { halfW, -halfD }, { -halfW, -halfD },
		{ 0, halfD }, { 0, -halfD }, { halfW, 0 }, { -halfW, 0 },
	}
	for _, offset in ipairs(posts) do
		makePart(model, "Mullion", Vector3.new(0.6, h, 0.6), Vector3.new(cx + offset[1], h / 2, cz + offset[2]), METAL_COLOR, Enum.Material.Metal, false)
	end
	-- Floor lines so it doesn't read as one flat slab.
	local y = 6
	while y < h - 2 do
		makePart(model, "FloorLine", Vector3.new(w + 0.2, 0.3, d + 0.2), Vector3.new(cx, y, cz), METAL_COLOR, Enum.Material.Metal, false)
		y = y + 6
	end
	addRoof(model, rng, cx, h, cz, w, d)
end

local function buildShop(model, rng, cx, cz, w, d, h, facades)
	box(model, "Shop", cx, 0, cz, w, h, d, pick(rng, facades), PLASTER)
	local front = makePart(model, "Storefront", Vector3.new(w + 0.3, 3.2, d + 0.3), Vector3.new(cx, 2.1, cz), WINDOW_COLOR, Enum.Material.Glass, false)
	front.Reflectance = 0.2
	makePart(model, "Awning", Vector3.new(w + 2.4, 0.4, d + 2.4), Vector3.new(cx, 4.1, cz), pick(rng, AWNING_COLORS), Enum.Material.Fabric, false)
	addRoof(model, rng, cx, h, cz, w, d)
end

local function buildPark(model, rng, cx, cz, size)
	makePart(model, "Grass", Vector3.new(size, 0.4, size), Vector3.new(cx, 0.2, cz), Color3.fromRGB(86, 150, 70), Enum.Material.Grass)
	local trees = rng:NextInteger(2, 5)
	for _ = 1, trees do
		local tx = cx + rng:NextNumber(-size / 2 + 3, size / 2 - 3)
		local tz = cz + rng:NextNumber(-size / 2 + 3, size / 2 - 3)
		local trunkH = rng:NextNumber(4, 7)
		makePart(model, "Trunk", Vector3.new(0.9, trunkH, 0.9), Vector3.new(tx, 0.4 + trunkH / 2, tz), Color3.fromRGB(105, 75, 50), Enum.Material.Wood)
		local canopySize = rng:NextNumber(5, 8)
		local canopy = makePart(model, "Leaves", Vector3.new(canopySize, canopySize, canopySize),
			Vector3.new(tx, 0.4 + trunkH + canopySize * 0.35, tz), Color3.fromRGB(60, 130 + rng:NextInteger(0, 40), 55), Enum.Material.Grass)
		canopy.Shape = Enum.PartType.Ball
	end
end

function BuildingGenerator.Generate(parent)
	local gridSize = Config.GRID_SIZE
	local mapSize = Config.MAP_SIZE_IN_GRIDS
	local lotSize = Config.BUILDING_SIZE
	local minH = Config.MIN_BUILDING_HEIGHT or 20
	local maxH = Config.MAX_BUILDING_HEIGHT or 120
	if maxH < minH then
		minH, maxH = maxH, minH
	end

	local facades = {}
	for _, c in ipairs(FACADE_COLORS) do
		table.insert(facades, c)
	end
	if type(Config.COLORS) == "table" then
		for _, c in ipairs(Config.COLORS) do
			if typeof(c) == "Color3" then
				table.insert(facades, c)
			end
		end
	end

	local rng = Random.new()
	local mapCenter = mapSize * gridSize / 2
	local maxDist = math.max(math.sqrt(2) * mapCenter, 1)

	for i = 0, mapSize - 1 do
		for j = 0, mapSize - 1 do
			local cellCenterX = (i * gridSize) + (gridSize / 2)
			local cellCenterZ = (j * gridSize) + (gridSize / 2)

			-- Same four lot positions per grid cell as the original template.
			local offsets = {
				Vector3.new(-lotSize / 2 - 2, 0, -lotSize / 2 - 2),
				Vector3.new(lotSize / 2 + 2, 0, -lotSize / 2 - 2),
				Vector3.new(-lotSize / 2 - 2, 0, lotSize / 2 + 2),
				Vector3.new(lotSize / 2 + 2, 0, lotSize / 2 + 2),
			}

			for _, offset in ipairs(offsets) do
				local lotX = cellCenterX + offset.X
				local lotZ = cellCenterZ + offset.Z
				local dist = math.sqrt((lotX - mapCenter) ^ 2 + (lotZ - mapCenter) ^ 2)
				local downtown = 1 - math.clamp(dist / maxDist, 0, 1) -- 1 at the center, 0 at the edge

				local model = Instance.new("Model")
				local roll = rng:NextNumber()
				local towerChance = 0.1 + 0.35 * downtown

				if roll < 0.07 then
					model.Name = "Park"
					buildPark(model, rng, lotX, lotZ, lotSize * 0.95)
				else
					local isGlass = roll >= 0.2 and roll < 0.2 + towerChance and rng:NextNumber() < 0.5
					local fracMin = isGlass and 0.55 or 0.62
					local fracMax = isGlass and 0.8 or 0.95
					local w = lotSize * rng:NextNumber(fracMin, fracMax)
					local d = lotSize * rng:NextNumber(fracMin, fracMax)
					-- Nudge within the lot so buildings don't line up perfectly,
					-- but never past the lot's own edges.
					local cx = lotX + rng:NextNumber(-(lotSize - w) / 2, (lotSize - w) / 2)
					local cz = lotZ + rng:NextNumber(-(lotSize - d) / 2, (lotSize - d) / 2)

					if roll < 0.2 then
						model.Name = "Shop"
						buildShop(model, rng, cx, cz, w, d, rng:NextNumber(8, 14), facades)
					elseif roll < 0.2 + towerChance then
						if isGlass then
							model.Name = "GlassTower"
							local h = lerp(minH, maxH, 0.55 + 0.45 * rng:NextNumber()) * (0.7 + 0.3 * downtown)
							buildGlassTower(model, rng, cx, cz, w, d, math.max(h, minH))
						else
							model.Name = "SteppedTower"
							local baseH = lerp(minH, maxH, rng:NextNumber(0.25, 0.45))
							local upperH = lerp(minH, maxH, rng:NextNumber(0.3, 0.6)) * (0.6 + 0.4 * downtown)
							buildSteppedTower(model, rng, cx, cz, w, d, baseH, upperH, facades)
						end
					else
						model.Name = "Apartment"
						local maxFloors = math.max(3, math.floor(lerp(minH, maxH, 0.45) / 7))
						local floors = rng:NextInteger(3, maxFloors)
						buildApartment(model, rng, cx, cz, w, d, floors * 7, facades)
					end
				end

				model.Parent = parent
			end
		end
	end
end

return BuildingGenerator

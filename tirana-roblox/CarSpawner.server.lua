--[[
	CarSpawner - ONE Script in ServerScriptService. The whole car system:
	a catalog of real cars from a $0 starter up to ~$9 million, a cash
	economy (earn money by driving - faster cars earn more), a dealership
	(SpawnCarButton.client.lua draws its UI), and saving of cash + owned
	cars between sessions.

	- Every player spawns next to their last-used (or starter) car.
	- G opens the dealership, C respawns your car, E at a car to drive,
	  W/S gas/brake/reverse, A/D steer, Space to get out.
	- In Roblox Studio every car is free, so you can test them all.
	- Saving uses DataStores. In Studio that needs Game Settings ->
	  Security -> "Enable Studio Access to API Services"; without it the
	  game still works, it just doesn't save.

	Visuals: cars are built from parts, so they get each real car's body
	class, proportions and signature color rather than an exact replica.
	Performance (top speed, 0-100 km/h) comes from each car's real specs,
	scaled for the map. Prices are approximate real new prices in USD.

	Driving is arcade-style: an invisible "Root" box carries the physics,
	pushed by a LinearVelocity and AngularVelocity updated every frame -
	steadier than wheel-joint physics (can't flip, jitter, or get stuck).
	The car's front is its -Z side (Roblox's LookVector).
]]

local DataStoreService = game:GetService("DataStoreService")
local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local ServerStorage = game:GetService("ServerStorage")
local Workspace = game:GetService("Workspace")

-- Real brand names are fine for a private/test game, but a PUBLIC game
-- using them can be taken down by Roblox for trademark reasons. Set this
-- to false before publishing to show made-up names instead.
local USE_REAL_NAMES = true

local STARTING_CASH = 2500
local CASH_PER_STUD = 0.5 -- $ earned per stud driven (faster car = more $/second)
local FREE_CARS_IN_STUDIO = true
local SPEED_SCALE = 0.8 -- real top speed (m/s) -> game studs/second
local ACCEL_SCALE = 1.6
local BRAKING = 70
local COASTING = 10
local SPAWN_COOLDOWN = 2
local AUTO_SPAWN_DELAY = 2
local AUTOSAVE_SECONDS = 60
local STARTER_CAR = "mercedes190e"
-- Real 3D models are scaled to this many times the block car's length.
-- Bigger = roomier to drive and easier to see; 1 = block-car size.
local MODEL_SIZE_SCALE = 1.35

-- id, real name, made-up name, approx price (USD), body class, top speed (km/h), 0-100 km/h (s), color
local CATALOG = {
	{ "mercedes190e", "Mercedes-Benz 190E (1990, used)", "Classic 190", 0, "sedan", 195, 11.0, Color3.fromRGB(176, 180, 186) },
	{ "sandero", "Dacia Sandero", "City Hatch", 15000, "hatch", 175, 12.0, Color3.fromRGB(214, 118, 44) },
	{ "corolla", "Toyota Corolla", "Family Sedan", 22000, "sedan", 180, 9.2, Color3.fromRGB(236, 236, 238) },
	{ "civic", "Honda Civic", "Compact Sport", 25000, "sedan", 200, 8.5, Color3.fromRGB(40, 80, 160) },
	{ "golfgti", "Volkswagen Golf GTI", "Hot Hatch", 32000, "hatch", 250, 6.2, Color3.fromRGB(190, 25, 30) },
	{ "mustang", "Ford Mustang GT", "Muscle V8", 42000, "sports", 250, 4.6, Color3.fromRGB(240, 190, 20) },
	{ "cclass", "Mercedes-Benz C-Class", "Executive Sedan", 48000, "sedan", 250, 7.1, Color3.fromRGB(22, 22, 26) },
	{ "bmwm3", "BMW M3", "Sport Sedan M", 77000, "sedan", 290, 3.9, Color3.fromRGB(60, 120, 70) },
	{ "teslaplaid", "Tesla Model S Plaid", "Electric Rocket", 90000, "sedan", 322, 2.1, Color3.fromRGB(170, 20, 25) },
	{ "rangerover", "Range Rover", "Luxury 4x4", 110000, "luxsuv", 242, 5.9, Color3.fromRGB(40, 60, 50) },
	{ "porsche911", "Porsche 911 Carrera", "Rear-Engine GT", 120000, "sports", 293, 4.1, Color3.fromRGB(175, 178, 182) },
	{ "g63", "Mercedes-AMG G 63", "Box 4x4", 180000, "luxsuv", 220, 4.5, Color3.fromRGB(18, 18, 20) },
	{ "urus", "Lamborghini Urus", "Super SUV", 230000, "suv", 305, 3.5, Color3.fromRGB(245, 200, 20) },
	{ "ferrari296", "Ferrari 296 GTB", "Italian V6 Hybrid", 320000, "supercar", 330, 2.9, Color3.fromRGB(200, 15, 20) },
	{ "cullinan", "Rolls-Royce Cullinan", "Royal SUV", 350000, "luxsuv", 250, 5.2, Color3.fromRGB(25, 35, 70) },
	{ "mclaren765", "McLaren 765LT", "Longtail", 380000, "supercar", 330, 2.8, Color3.fromRGB(255, 120, 20) },
	{ "phantom", "Rolls-Royce Phantom", "Royal Limousine", 460000, "luxury", 250, 5.3, Color3.fromRGB(235, 232, 225) },
	{ "revuelto", "Lamborghini Revuelto", "V12 Bull", 600000, "supercar", 350, 2.5, Color3.fromRGB(80, 170, 40) },
	{ "senna", "McLaren Senna", "Track Weapon", 1000000, "hypercar", 335, 2.8, Color3.fromRGB(250, 250, 250) },
	{ "laferrari", "Ferrari LaFerrari", "Hybrid V12 Icon", 1400000, "hypercar", 350, 2.4, Color3.fromRGB(190, 10, 15) },
	{ "huayra", "Pagani Huayra", "Carbon Artwork", 2800000, "hypercar", 383, 2.8, Color3.fromRGB(120, 125, 135) },
	{ "chiron", "Bugatti Chiron", "W16 Hypercar", 3000000, "hypercar", 420, 2.4, Color3.fromRGB(20, 60, 150) },
	{ "jesko", "Koenigsegg Jesko Absolut", "Swedish Missile", 3000000, "hypercar", 480, 2.5, Color3.fromRGB(235, 235, 240) },
	{ "divo", "Bugatti Divo", "Aero Hypercar", 5800000, "hypercar", 380, 2.4, Color3.fromRGB(70, 150, 210) },
	{ "centodieci", "Bugatti Centodieci", "The 10 Million", 9000000, "hypercar", 380, 2.4, Color3.fromRGB(240, 240, 242) },
}

-- Body shape per class. All heights are above the ground.
-- L/W = length/width, clearance = gap under the body, bodyH = lower body
-- height, cabinL/H/Z = glasshouse length/height/offset (+Z = rear),
-- wheelR = wheel radius, turn = steering rate (degrees/second).
local CLASSES = {
	hatch = { L = 11, W = 5.8, clearance = 0.9, bodyH = 1.9, cabinL = 5.4, cabinH = 1.9, cabinZ = 1.1, wedgeL = 1.4, wheelR = 1.2, turn = 95 },
	sedan = { L = 13, W = 6, clearance = 0.9, bodyH = 1.8, cabinL = 5.8, cabinH = 1.8, cabinZ = 0.6, wedgeL = 1.8, wheelR = 1.25, turn = 90 },
	sports = { L = 12.8, W = 6.2, clearance = 0.7, bodyH = 1.6, cabinL = 4.6, cabinH = 1.5, cabinZ = 1.1, wedgeL = 2.2, wheelR = 1.3, turn = 100, spoiler = "lip" },
	supercar = { L = 13.5, W = 6.8, clearance = 0.55, bodyH = 1.4, cabinL = 4.2, cabinH = 1.3, cabinZ = -0.2, wedgeL = 2.6, wheelR = 1.3, turn = 105, spoiler = "lip", intakes = true },
	hypercar = { L = 14, W = 7, clearance = 0.5, bodyH = 1.35, cabinL = 4, cabinH = 1.25, cabinZ = -0.3, wedgeL = 2.8, wheelR = 1.35, turn = 105, spoiler = "wing", intakes = true },
	suv = { L = 13.5, W = 6.6, clearance = 1.4, bodyH = 2.4, cabinL = 7, cabinH = 2, cabinZ = 0.8, wedgeL = 1.6, wheelR = 1.6, turn = 85 },
	luxsuv = { L = 14.5, W = 6.8, clearance = 1.5, bodyH = 2.7, cabinL = 8.2, cabinH = 2.3, cabinZ = 1, wedgeL = 0.9, wheelR = 1.7, turn = 75, chrome = true },
	luxury = { L = 15.5, W = 6.6, clearance = 0.9, bodyH = 2, cabinL = 7.2, cabinH = 2, cabinZ = 0.8, wedgeL = 1.6, wheelR = 1.4, turn = 80, chrome = true },
}

local carsById = {}
for _, entry in ipairs(CATALOG) do
	carsById[entry[1]] = {
		id = entry[1],
		name = USE_REAL_NAMES and entry[2] or entry[3],
		price = entry[4],
		class = entry[5],
		topSpeed = entry[6],
		zeroTo100 = entry[7],
		color = entry[8],
	}
end

local GLASS_COLOR = Color3.fromRGB(35, 45, 58)
local TRIM_COLOR = Color3.fromRGB(28, 28, 32)
local RIM_COLOR = Color3.fromRGB(190, 192, 198)
local CHROME_COLOR = Color3.fromRGB(215, 218, 224)

local function safeMaterial(name, fallback)
	local ok, material = pcall(function()
		return Enum.Material[name]
	end)
	if ok and material then
		return material
	end
	return fallback
end

local RUBBER = safeMaterial("Rubber", Enum.Material.SmoothPlastic)

local function getRemote(className, name)
	local remote = ReplicatedStorage:FindFirstChild(name)
	if not remote then
		remote = Instance.new(className)
		remote.Name = name
		remote.Parent = ReplicatedStorage
	end
	return remote
end

local spawnEvent = getRemote("RemoteEvent", "SpawnTiranaCar")
local shopFunction = getRemote("RemoteFunction", "TiranaCarShop")

local carsFolder = Workspace:FindFirstChild("TiranaCars")
if not carsFolder then
	carsFolder = Instance.new("Folder")
	carsFolder.Name = "TiranaCars"
	carsFolder.Parent = Workspace
end

---------------------------------------------------------------------
-- Building a car
---------------------------------------------------------------------

-- Real 3D models: put a Model (e.g. from the Toolbox) in
-- ServerStorage > CarModels, named exactly a car's id ("chiron",
-- "urus", ...). It replaces that car's block body; cars without one keep
-- the block body. If a model drives backwards or sideways, give it a
-- Number attribute "YawOffset" (e.g. 180 or 90).
local function getCustomBody(carId)
	local folder = ServerStorage:FindFirstChild("CarModels")
	local template = folder and folder:FindFirstChild(carId)
	if template and (template:IsA("Model") or template:IsA("BasePart")) then
		return template
	end
	return nil
end

-- Anything that would fight our driving system or let players sit in
-- the wrong place: Toolbox cars often ship with their own chassis
-- scripts, seats, joints and physics movers.
local STRIP_CLASSES = {
	"BaseScript", "ModuleScript", "Seat", "VehicleSeat", "JointInstance", "Constraint",
	"WeldConstraint", "NoCollisionConstraint", "BodyMover", "ProximityPrompt", "ClickDetector", "Humanoid",
}

-- Clones `template`, strips it, scales it to `targetLength` studs long,
-- turns its long side along the car's length, sets its wheels on the
-- ground, and adds its parts to `model`/`parts`. Returns its final size
-- as (width, height, length).
local function attachCustomBody(template, rootCFrame, targetLength, model, parts)
	local clone = template:Clone()
	if clone:IsA("BasePart") then
		local wrapper = Instance.new("Model")
		wrapper.Name = template.Name
		clone.Parent = wrapper
		clone = wrapper
	end

	local toRemove = {}
	for _, descendant in ipairs(clone:GetDescendants()) do
		for _, className in ipairs(STRIP_CLASSES) do
			if descendant:IsA(className) then
				table.insert(toRemove, descendant)
				break
			end
		end
	end
	for _, instance in ipairs(toRemove) do
		instance:Destroy()
	end

	local bodyParts = {}
	for _, descendant in ipairs(clone:GetDescendants()) do
		if descendant:IsA("BasePart") then
			table.insert(bodyParts, descendant)
		end
	end
	if #bodyParts == 0 then
		error("the model has no parts")
	end

	local boxCFrame, size = clone:GetBoundingBox()
	local longest = math.max(size.X, size.Z)
	if longest <= 0 then
		error("the model has no size")
	end
	local scaled = pcall(function()
		clone:ScaleTo(clone:GetScale() * (targetLength / longest))
	end)
	if not scaled then
		warn("[TiranaCars] Couldn't resize " .. template.Name .. " - using it at its original size.")
	end
	boxCFrame, size = clone:GetBoundingBox()

	local alongX = size.X > size.Z
	local alignLong = alongX and CFrame.Angles(0, math.rad(90), 0) or CFrame.new()
	local yaw = tonumber(template:GetAttribute("YawOffset")) or 0
	local target = rootCFrame * CFrame.new(0, size.Y / 2 - 0.5, 0) * CFrame.Angles(0, math.rad(yaw), 0) * alignLong
	clone:PivotTo(target * boxCFrame:Inverse() * clone:GetPivot())

	for _, p in ipairs(bodyParts) do
		p.Anchored = true
		p.CanCollide = false
		p.CanQuery = false
		p.Massless = true
		table.insert(parts, p)
	end
	clone.Name = "Body"
	clone.Parent = model

	if alongX then
		return Vector3.new(size.Z, size.Y, size.X)
	end
	return size
end

-- rootCFrame is where the invisible physics box sits: its center is 0.5
-- studs above the ground, so a part at height h above the ground is at
-- y = h - 0.5 relative to the root.
local function buildCar(car, rootCFrame)
	local shape = CLASSES[car.class] or CLASSES.sedan
	local L, W = shape.L, shape.W
	local template = getCustomBody(car.id)
	-- Model cars are drawn bigger than block cars; the physics box grows to match.
	local sizeScale = template and MODEL_SIZE_SCALE or 1
	local bodyTop = shape.clearance + shape.bodyH
	local paint = car.color

	local model = Instance.new("Model")
	model.Name = car.name

	local root = Instance.new("Part")
	root.Name = "Root"
	root.Size = Vector3.new(W * sizeScale - 0.4, 1, L * sizeScale - 1)
	root.CFrame = rootCFrame
	root.Transparency = 1
	root.CanCollide = true
	root.Anchored = true
	root.CustomPhysicalProperties = PhysicalProperties.new(0.7, 0.05, 0, 100, 1)
	root.Parent = model
	model.PrimaryPart = root

	-- Headlights: the root's Front face is the car's front.
	local headlight = Instance.new("SpotLight")
	headlight.Face = Enum.NormalId.Front
	headlight.Range = 60
	headlight.Angle = 70
	headlight.Brightness = 4
	headlight.Color = Color3.fromRGB(255, 244, 214)
	headlight.Shadows = false
	headlight.Parent = root

	local parts = {}

	local function add(className, name, size, x, heightAboveGround, z, color, material, rotation)
		local p = Instance.new(className)
		p.Name = name
		p.Size = size
		local offset = CFrame.new(x, heightAboveGround - 0.5, z)
		if rotation then
			offset = offset * rotation
		end
		p.CFrame = rootCFrame * offset
		p.Color = color
		p.Material = material
		p.Anchored = true
		p.CanCollide = false
		p.Massless = true
		p.TopSurface = Enum.SurfaceType.Smooth
		p.BottomSurface = Enum.SurfaceType.Smooth
		p.Parent = model
		table.insert(parts, p)
		return p
	end

	local seatX, seatHeight, seatZ = -(W / 2 - 1.6), bodyTop - 0.3, shape.cabinZ
	local usedCustom = false
	if template then
		local ok, result = pcall(attachCustomBody, template, rootCFrame, L * sizeScale, model, parts)
		if ok then
			usedCustom = true
			-- Rough driver position inside an arbitrary model: left of center,
			-- about a third of the way up, just behind the middle.
			seatX, seatHeight, seatZ = -result.X * 0.18, result.Y * 0.3, result.Z * 0.05
		else
			warn("[TiranaCars] Couldn't use the 3D model for " .. car.id .. " (using the block body instead): " .. tostring(result))
			root.Size = Vector3.new(W - 0.4, 1, L - 1)
		end
	end

	if not usedCustom then
		local body = add("Part", "Body", Vector3.new(W, shape.bodyH, L), 0, shape.clearance + shape.bodyH / 2, 0, paint, Enum.Material.SmoothPlastic)
		body.Reflectance = 0.12

		-- Glasshouse. A WedgePart is full height at its +Z side and slopes
		-- down to -Z, so unrotated in front of the cabin it's a windshield.
		local cabinY = bodyTop + shape.cabinH / 2
		local cabinW = W - 0.6
		local cabin = add("Part", "Cabin", Vector3.new(cabinW, shape.cabinH, shape.cabinL), 0, cabinY, shape.cabinZ, GLASS_COLOR, Enum.Material.Glass)
		cabin.Transparency = 0.25
		local frontZ = shape.cabinZ - shape.cabinL / 2 - shape.wedgeL / 2
		local rearZ = shape.cabinZ + shape.cabinL / 2 + shape.wedgeL / 2
		local windshield = add("WedgePart", "Windshield", Vector3.new(cabinW, shape.cabinH, shape.wedgeL), 0, cabinY, frontZ, GLASS_COLOR, Enum.Material.Glass)
		windshield.Transparency = 0.25
		local rearWindow = add("WedgePart", "RearWindow", Vector3.new(cabinW, shape.cabinH, shape.wedgeL), 0, cabinY, rearZ, GLASS_COLOR, Enum.Material.Glass, CFrame.Angles(0, math.pi, 0))
		rearWindow.Transparency = 0.25
		add("Part", "Roof", Vector3.new(cabinW + 0.2, 0.3, shape.cabinL - 0.2), 0, bodyTop + shape.cabinH + 0.15, shape.cabinZ, paint, Enum.Material.SmoothPlastic)

		-- Front and back
		local bumperH = shape.clearance + 0.35
		add("Part", "FrontBumper", Vector3.new(W + 0.2, 0.6, 0.5), 0, bumperH, -L / 2 - 0.2, TRIM_COLOR, Enum.Material.SmoothPlastic)
		add("Part", "RearBumper", Vector3.new(W + 0.2, 0.6, 0.5), 0, bumperH, L / 2 + 0.2, TRIM_COLOR, Enum.Material.SmoothPlastic)
		local lightH = shape.clearance + shape.bodyH * 0.65
		local grilleColor = shape.chrome and CHROME_COLOR or TRIM_COLOR
		local grilleW = shape.chrome and 2.6 or 2.2
		local grilleH = shape.chrome and shape.bodyH * 0.6 or 0.5
		add("Part", "Grille", Vector3.new(grilleW, grilleH, 0.12), 0, shape.clearance + shape.bodyH * 0.45, -L / 2 - 0.05, grilleColor, Enum.Material.Metal)
		for _, side in ipairs({ -1, 1 }) do
			local lx = side * (W / 2 - 0.9)
			add("Part", "Headlight", Vector3.new(1.3, 0.45, 0.15), lx, lightH, -L / 2 - 0.05, Color3.fromRGB(255, 244, 214), Enum.Material.Neon)
			add("Part", "Taillight", Vector3.new(1.3, 0.45, 0.15), lx, lightH, L / 2 + 0.05, Color3.fromRGB(210, 20, 20), Enum.Material.Neon)
			if shape.intakes then
				add("Part", "SideIntake", Vector3.new(0.15, shape.bodyH * 0.5, 2.2), side * (W / 2 + 0.05), shape.clearance + shape.bodyH * 0.5, L * 0.12, TRIM_COLOR, Enum.Material.SmoothPlastic)
			end
			if shape.chrome then
				add("Part", "ChromeStrip", Vector3.new(0.1, 0.18, L * 0.8), side * (W / 2 + 0.03), shape.clearance + shape.bodyH * 0.35, 0, CHROME_COLOR, Enum.Material.Metal)
			end
		end

		if shape.spoiler == "lip" then
			add("Part", "Spoiler", Vector3.new(W - 0.8, 0.2, 0.9), 0, bodyTop + 0.2, L / 2 - 0.5, paint, Enum.Material.SmoothPlastic)
		elseif shape.spoiler == "wing" then
			for _, side in ipairs({ -1, 1 }) do
				add("Part", "WingPost", Vector3.new(0.25, 1.2, 0.5), side * (W / 2 - 1.4), bodyTop + 0.6, L / 2 - 0.9, TRIM_COLOR, Enum.Material.SmoothPlastic)
			end
			add("Part", "Wing", Vector3.new(W - 0.4, 0.2, 1.3), 0, bodyTop + 1.25, L / 2 - 0.9, TRIM_COLOR, Enum.Material.SmoothPlastic)
		end

		-- Wheels: a Cylinder's round faces are on its local X axis, already
		-- the car's side-to-side axis, so they need no rotation.
		local axleZ = L / 2 - shape.wheelR - 1
		local wheelX = W / 2 - 0.35
		for _, x in ipairs({ -wheelX, wheelX }) do
			for _, z in ipairs({ -axleZ, axleZ }) do
				local d = shape.wheelR * 2
				local tire = add("Part", "Tire", Vector3.new(1.1, d, d), x, shape.wheelR, z, Color3.fromRGB(22, 22, 24), RUBBER)
				tire.Shape = Enum.PartType.Cylinder
				local rim = add("Part", "Rim", Vector3.new(1.15, d * 0.6, d * 0.6), x, shape.wheelR, z, RIM_COLOR, Enum.Material.Metal)
				rim.Shape = Enum.PartType.Cylinder
			end
		end
	end

	-- Driver's seat on the left (Albania drives on the right).
	local seat = Instance.new("VehicleSeat")
	seat.Name = "DriverSeat"
	seat.Size = Vector3.new(2, 0.6, 2)
	seat.CFrame = rootCFrame * CFrame.new(seatX, seatHeight - 0.5, seatZ)
	seat.Transparency = 1
	seat.CanCollide = false
	seat.Massless = true
	seat.Anchored = true
	seat.HeadsUpDisplay = false
	seat.Parent = model
	table.insert(parts, seat)

	local prompt = Instance.new("ProximityPrompt")
	prompt.ActionText = "Drive"
	prompt.ObjectText = car.name
	prompt.HoldDuration = 0
	prompt.MaxActivationDistance = 12
	prompt.RequiresLineOfSight = false
	prompt.Parent = seat

	-- Parent first, then weld, then unanchor - welding parts that aren't
	-- in the workspace yet is the classic way to get a car that falls
	-- apart on spawn.
	model.Parent = carsFolder
	for _, p in ipairs(parts) do
		local weld = Instance.new("WeldConstraint")
		weld.Part0 = root
		weld.Part1 = p
		weld.Parent = p
	end

	local attachment = Instance.new("Attachment")
	attachment.Name = "DriveAttachment"
	attachment.Parent = root

	local linear = Instance.new("LinearVelocity")
	linear.Name = "Drive"
	linear.Attachment0 = attachment
	linear.RelativeTo = Enum.ActuatorRelativeTo.World
	linear.VelocityConstraintMode = Enum.VelocityConstraintMode.Plane
	linear.PrimaryTangentAxis = Vector3.new(1, 0, 0)
	linear.SecondaryTangentAxis = Vector3.new(0, 0, 1)
	linear.PlaneVelocity = Vector2.new(0, 0)
	linear.MaxForce = 120000
	linear.Parent = root

	-- Also holds pitch/roll at zero, which keeps the car from tipping over.
	local angular = Instance.new("AngularVelocity")
	angular.Name = "Steer"
	angular.Attachment0 = attachment
	angular.RelativeTo = Enum.ActuatorRelativeTo.World
	angular.AngularVelocity = Vector3.new(0, 0, 0)
	angular.MaxTorque = 120000
	angular.Parent = root

	for _, p in ipairs(parts) do
		p.Anchored = false
	end
	root.Anchored = false

	return {
		model = model,
		root = root,
		seat = seat,
		prompt = prompt,
		linear = linear,
		angular = angular,
		speed = 0,
		maxSpeed = car.topSpeed / 3.6 * SPEED_SCALE,
		maxReverse = 20,
		acceleration = (100 / 3.6) / car.zeroTo100 * ACCEL_SCALE,
		turnRate = math.rad(shape.turn),
	}
end

---------------------------------------------------------------------
-- Player data: cash + owned cars, saved between sessions
---------------------------------------------------------------------

local store = nil
do
	local ok, result = pcall(function()
		return DataStoreService:GetDataStore("TiranaCarsV1")
	end)
	if ok then
		store = result
	else
		warn("[TiranaCars] Saving disabled (DataStores unavailable): " .. tostring(result))
	end
end

local profiles = {}

local function isFree()
	return FREE_CARS_IN_STUDIO and RunService:IsStudio()
end

local function ownsCar(player, carId)
	local profile = profiles[player]
	if not profile then
		return false
	end
	return isFree() or profile.owned[carId] == true
end

local function saveProfile(player)
	local profile = profiles[player]
	if not store or not profile or not profile.loaded then
		return
	end
	local ok, err = pcall(function()
		store:SetAsync("player_" .. player.UserId, {
			cash = math.floor(profile.cash),
			owned = profile.owned,
			lastCar = profile.lastCar,
		})
	end)
	if not ok then
		warn("[TiranaCars] Couldn't save " .. player.Name .. ": " .. tostring(err))
	end
end

local function loadProfile(player)
	local profile = { cash = STARTING_CASH, owned = { [STARTER_CAR] = true }, lastCar = STARTER_CAR, loaded = false, cashRemainder = 0 }
	if store then
		local ok, data = pcall(function()
			return store:GetAsync("player_" .. player.UserId)
		end)
		if ok then
			if type(data) == "table" then
				profile.cash = tonumber(data.cash) or STARTING_CASH
				if type(data.owned) == "table" then
					for id, value in pairs(data.owned) do
						if carsById[id] and value == true then
							profile.owned[id] = true
						end
					end
				end
				if type(data.lastCar) == "string" and carsById[data.lastCar] then
					profile.lastCar = data.lastCar
				end
			end
			profile.loaded = true
		else
			-- Don't mark as loaded, so a failed load never overwrites
			-- real saved progress with starting values.
			warn("[TiranaCars] Couldn't load " .. player.Name .. "'s save (progress won't be saved this session): " .. tostring(data))
		end
	end
	profiles[player] = profile

	local leaderstats = Instance.new("Folder")
	leaderstats.Name = "leaderstats"
	local cashValue = Instance.new("IntValue")
	cashValue.Name = "Cash"
	cashValue.Value = math.floor(profile.cash)
	cashValue.Parent = leaderstats
	leaderstats.Parent = player
	profile.cashValue = cashValue
	return profile
end

local function setCash(player, amount)
	local profile = profiles[player]
	if profile then
		profile.cash = amount
		if profile.cashValue then
			profile.cashValue.Value = math.floor(amount)
		end
	end
end

---------------------------------------------------------------------
-- Spawning
---------------------------------------------------------------------

local carsByPlayer = {}
local activeCars = {}
local lastSpawn = {}

local function removeCar(player)
	local active = carsByPlayer[player]
	if active then
		activeCars[active] = nil
		active.model:Destroy()
		carsByPlayer[player] = nil
	end
end

-- Tries a few spots around the player and picks the first one whose
-- ground is at street level, so the car doesn't land on a rooftop.
local function findSpawnCFrame(character)
	local hrp = character:FindFirstChild("HumanoidRootPart")
	if not hrp then
		return nil
	end

	local look = Vector3.new(hrp.CFrame.LookVector.X, 0, hrp.CFrame.LookVector.Z)
	if look.Magnitude < 0.01 then
		look = Vector3.new(0, 0, -1)
	end
	look = look.Unit
	local right = Vector3.new(-look.Z, 0, look.X)
	local feetY = hrp.Position.Y - 3

	local params = RaycastParams.new()
	params.FilterType = Enum.RaycastFilterType.Exclude
	params.FilterDescendantsInstances = { character, carsFolder }

	local candidates = { look * 15, right * 11, -right * 11, -look * 15 }
	for _, offset in ipairs(candidates) do
		local origin = hrp.Position + offset + Vector3.new(0, 30, 0)
		local result = Workspace:Raycast(origin, Vector3.new(0, -80, 0), params)
		if result and math.abs(result.Position.Y - feetY) < 4 then
			local pos = Vector3.new(origin.X, result.Position.Y + 0.6, origin.Z)
			return CFrame.lookAt(pos, pos + look)
		end
	end

	local fallback = Vector3.new(hrp.Position.X, feetY + 0.6, hrp.Position.Z) + look * 9
	return CFrame.lookAt(fallback, fallback + look)
end

local function spawnCarFor(player, carId)
	local profile = profiles[player]
	local character = player.Character
	if not profile or not character then
		return
	end
	carId = carId or profile.lastCar
	if not carsById[carId] or not ownsCar(player, carId) then
		carId = STARTER_CAR
	end
	local cframe = findSpawnCFrame(character)
	if not cframe then
		return
	end

	removeCar(player)
	local ok, active = pcall(buildCar, carsById[carId], cframe)
	if not ok then
		warn("[TiranaCars] Building " .. carId .. " failed: " .. tostring(active))
		return
	end
	active.owner = player
	carsByPlayer[player] = active
	activeCars[active] = true
	profile.lastCar = carId
	pcall(function()
		active.root:SetNetworkOwner(nil)
	end)

	active.prompt.Triggered:Connect(function(who)
		local whoCharacter = who.Character
		local humanoid = whoCharacter and whoCharacter:FindFirstChildOfClass("Humanoid")
		if humanoid and not active.seat.Occupant then
			active.seat:Sit(humanoid)
		end
	end)
	active.seat:GetPropertyChangedSignal("Occupant"):Connect(function()
		active.prompt.Enabled = active.seat.Occupant == nil
	end)
end

spawnEvent.OnServerEvent:Connect(function(player, carId)
	local now = os.clock()
	if lastSpawn[player] and now - lastSpawn[player] < SPAWN_COOLDOWN then
		return
	end
	lastSpawn[player] = now
	if type(carId) ~= "string" then
		carId = nil
	end
	spawnCarFor(player, carId)
end)

---------------------------------------------------------------------
-- Dealership
---------------------------------------------------------------------

local function catalogFor(player)
	local list = {}
	for _, entry in ipairs(CATALOG) do
		local car = carsById[entry[1]]
		table.insert(list, {
			id = car.id,
			name = car.name,
			price = car.price,
			class = car.class,
			topSpeed = car.topSpeed,
			zeroTo100 = car.zeroTo100,
			owned = ownsCar(player, car.id),
			hasModel = getCustomBody(car.id) ~= nil,
		})
	end
	return list
end

shopFunction.OnServerInvoke = function(player, action, carId)
	local profile = profiles[player]
	if not profile then
		return { ok = false, message = "Still loading, try again in a second." }
	end

	if action == "buy" then
		local car = type(carId) == "string" and carsById[carId]
		if not car then
			return { ok = false, message = "Unknown car." }
		end
		if ownsCar(player, car.id) then
			return { ok = true, message = "You already own the " .. car.name .. "." }
		end
		if profile.cash < car.price then
			return { ok = false, message = "Not enough cash for the " .. car.name .. "." }
		end
		setCash(player, profile.cash - car.price)
		profile.owned[car.id] = true
		saveProfile(player)
		return { ok = true, message = "You bought the " .. car.name .. "!", catalog = catalogFor(player) }
	end

	return { ok = true, catalog = catalogFor(player), free = isFree() }
end

---------------------------------------------------------------------
-- Players joining/leaving, autosave
---------------------------------------------------------------------

local function onPlayerAdded(player)
	loadProfile(player)
	player.CharacterAdded:Connect(function()
		task.wait(AUTO_SPAWN_DELAY)
		spawnCarFor(player)
	end)
	if player.Character then
		task.delay(AUTO_SPAWN_DELAY, spawnCarFor, player)
	end
end

Players.PlayerAdded:Connect(onPlayerAdded)
for _, player in ipairs(Players:GetPlayers()) do
	onPlayerAdded(player)
end

Players.PlayerRemoving:Connect(function(player)
	saveProfile(player)
	removeCar(player)
	profiles[player] = nil
	lastSpawn[player] = nil
end)

game:BindToClose(function()
	for _, player in ipairs(Players:GetPlayers()) do
		saveProfile(player)
	end
end)

task.spawn(function()
	while true do
		task.wait(AUTOSAVE_SECONDS)
		for _, player in ipairs(Players:GetPlayers()) do
			saveProfile(player)
		end
	end
end)

---------------------------------------------------------------------
-- Driving + earning, every frame
---------------------------------------------------------------------

local function moveToward(value, target, maxDelta)
	if value < target then
		return math.min(value + maxDelta, target)
	end
	return math.max(value - maxDelta, target)
end

RunService.Heartbeat:Connect(function(dt)
	for active in pairs(activeCars) do
		if not active.root.Parent or active.root.Position.Y < -100 then
			activeCars[active] = nil
			if active.model.Parent then
				active.model:Destroy()
			end
		else
			local occupied = active.seat.Occupant ~= nil
			local throttle = occupied and active.seat.ThrottleFloat or 0
			local steer = occupied and active.seat.SteerFloat or 0

			local target = throttle >= 0 and throttle * active.maxSpeed or throttle * active.maxReverse
			local rate
			if active.speed ~= 0 and target ~= 0 and (target > 0) ~= (active.speed > 0) then
				rate = BRAKING
			elseif math.abs(target) > math.abs(active.speed) then
				rate = active.acceleration
			else
				rate = COASTING
			end
			active.speed = moveToward(active.speed, target, rate * dt)

			-- Steering only works while moving, and flips when reversing.
			-- Positive yaw turns left, so D (+1) negates it.
			local turnFactor = math.clamp(math.abs(active.speed) / 12, 0, 1)
			local direction = active.speed >= 0 and 1 or -1
			active.angular.AngularVelocity = Vector3.new(0, -steer * active.turnRate * turnFactor * direction, 0)

			local forward = active.root.CFrame.LookVector
			local flat = Vector3.new(forward.X, 0, forward.Z)
			if flat.Magnitude > 0.01 then
				flat = flat.Unit * active.speed
			end
			active.linear.PlaneVelocity = Vector2.new(flat.X, flat.Z)

			-- Pay the driver for distance covered.
			if occupied and active.owner then
				local profile = profiles[active.owner]
				if profile then
					profile.cashRemainder = profile.cashRemainder + math.abs(active.speed) * dt * CASH_PER_STUD
					if profile.cashRemainder >= 1 then
						local whole = math.floor(profile.cashRemainder)
						profile.cashRemainder = profile.cashRemainder - whole
						setCash(active.owner, profile.cash + whole)
					end
				end
			end
		end
	end
end)

print("[TiranaCars] Car system ready - " .. #CATALOG .. " cars in the dealership.")

--[[
	CarSpawner - ONE Script in ServerScriptService. Everything the cars
	need is in this file (it no longer needs a separate CarBuilder
	ModuleScript), so there's only one thing to set up.

	- Every player automatically gets a car next to them a couple of
	  seconds after they spawn - no button needed.
	- The "Spawn Car (C)" button / C key (SpawnCarButton.client.lua,
	  optional) spawns a fresh one in front of you. One car per player.
	- Walk up to the car and press E ("Drive"). W/S gas/brake/reverse,
	  A/D steer, Space to get out.

	Driving is arcade-style: an invisible "Root" box carries the physics,
	pushed by a LinearVelocity (drive) and AngularVelocity (steering)
	updated every frame from the seat's input - steadier than wheel-joint
	physics (can't flip, jitter, or get stuck), with cosmetic wheels.
	The car's front is its -Z side (Roblox's LookVector).
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local Workspace = game:GetService("Workspace")

local MAX_SPEED = 70 -- studs/second (~1 stud = 1 meter, so ~250 km/h top speed)
local MAX_REVERSE = 25
local ACCELERATION = 30
local BRAKING = 70
local COASTING = 12
local TURN_RATE = math.rad(90) -- at full steer and speed
local SPAWN_COOLDOWN = 2
local AUTO_SPAWN_DELAY = 2

local PAINT_COLORS = {
	Color3.fromRGB(200, 30, 35),
	Color3.fromRGB(20, 20, 24),
	Color3.fromRGB(235, 235, 238),
	Color3.fromRGB(30, 75, 160),
	Color3.fromRGB(150, 155, 162),
	Color3.fromRGB(245, 190, 30),
	Color3.fromRGB(25, 110, 70),
}
local GLASS_COLOR = Color3.fromRGB(35, 45, 58)
local TRIM_COLOR = Color3.fromRGB(28, 28, 32)
local RIM_COLOR = Color3.fromRGB(190, 192, 198)

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

local spawnEvent = ReplicatedStorage:FindFirstChild("SpawnTiranaCar")
if not spawnEvent then
	spawnEvent = Instance.new("RemoteEvent")
	spawnEvent.Name = "SpawnTiranaCar"
	spawnEvent.Parent = ReplicatedStorage
end

local carsFolder = Workspace:FindFirstChild("TiranaCars")
if not carsFolder then
	carsFolder = Instance.new("Folder")
	carsFolder.Name = "TiranaCars"
	carsFolder.Parent = Workspace
end

-- Builds a car whose invisible physics box is centered at rootCFrame
-- (which should sit ~0.5 studs above the ground).
local function buildCar(rootCFrame)
	local rng = Random.new()
	local paint = PAINT_COLORS[rng:NextInteger(1, #PAINT_COLORS)]

	local model = Instance.new("Model")
	model.Name = "Car"

	local root = Instance.new("Part")
	root.Name = "Root"
	root.Size = Vector3.new(6, 1, 12)
	root.CFrame = rootCFrame
	root.Transparency = 1
	root.CanCollide = true
	root.Anchored = true
	-- Low friction so the velocity movers glide it instead of fighting
	-- ground friction every frame.
	root.CustomPhysicalProperties = PhysicalProperties.new(0.7, 0.05, 0, 100, 1)
	root.Parent = model
	model.PrimaryPart = root

	local parts = {}

	local function add(className, name, size, offset, color, material)
		local p = Instance.new(className)
		p.Name = name
		p.Size = size
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

	local body = add("Part", "Body", Vector3.new(6.2, 1.9, 12.8), CFrame.new(0, 1.45, 0), paint, Enum.Material.SmoothPlastic)
	body.Reflectance = 0.1

	-- A WedgePart is full height at its +Z side and slopes down to -Z, so
	-- an unrotated one in front of the cabin reads as a windshield.
	local cabin = add("Part", "Cabin", Vector3.new(5.6, 1.9, 6), CFrame.new(0, 3.35, 0.9), GLASS_COLOR, Enum.Material.Glass)
	cabin.Transparency = 0.25
	local windshield = add("WedgePart", "Windshield", Vector3.new(5.6, 1.9, 1.8), CFrame.new(0, 3.35, -3), GLASS_COLOR, Enum.Material.Glass)
	windshield.Transparency = 0.25
	local rearWindow = add("WedgePart", "RearWindow", Vector3.new(5.6, 1.9, 1.8), CFrame.new(0, 3.35, 4.8) * CFrame.Angles(0, math.pi, 0), GLASS_COLOR, Enum.Material.Glass)
	rearWindow.Transparency = 0.25
	add("Part", "Roof", Vector3.new(5.8, 0.3, 5.4), CFrame.new(0, 4.45, 1), paint, Enum.Material.SmoothPlastic)

	add("Part", "FrontBumper", Vector3.new(6.4, 0.6, 0.5), CFrame.new(0, 1, -6.55), TRIM_COLOR, Enum.Material.SmoothPlastic)
	add("Part", "RearBumper", Vector3.new(6.4, 0.6, 0.5), CFrame.new(0, 1, 6.55), TRIM_COLOR, Enum.Material.SmoothPlastic)
	add("Part", "Grille", Vector3.new(2.4, 0.6, 0.12), CFrame.new(0, 1.9, -6.45), TRIM_COLOR, Enum.Material.Metal)
	for _, x in ipairs({ -2.2, 2.2 }) do
		add("Part", "Headlight", Vector3.new(1.3, 0.5, 0.15), CFrame.new(x, 2, -6.45), Color3.fromRGB(255, 244, 214), Enum.Material.Neon)
		add("Part", "Taillight", Vector3.new(1.3, 0.5, 0.15), CFrame.new(x, 2, 6.45), Color3.fromRGB(210, 20, 20), Enum.Material.Neon)
	end

	-- A Cylinder's round faces are on its local X axis - already the
	-- car's side-to-side axis, so wheels need no rotation.
	for _, x in ipairs({ -2.95, 2.95 }) do
		for _, z in ipairs({ -4.1, 4.1 }) do
			local tire = add("Part", "Tire", Vector3.new(1.1, 2.6, 2.6), CFrame.new(x, 0.8, z), Color3.fromRGB(22, 22, 24), RUBBER)
			tire.Shape = Enum.PartType.Cylinder
			local rim = add("Part", "Rim", Vector3.new(1.15, 1.5, 1.5), CFrame.new(x, 0.8, z), RIM_COLOR, Enum.Material.Metal)
			rim.Shape = Enum.PartType.Cylinder
		end
	end

	-- Driver's seat on the left (Albania drives on the right).
	local seat = Instance.new("VehicleSeat")
	seat.Name = "DriverSeat"
	seat.Size = Vector3.new(2, 0.6, 2)
	seat.CFrame = rootCFrame * CFrame.new(-1.3, 2.7, 1)
	seat.Transparency = 1
	seat.CanCollide = false
	seat.Massless = true
	seat.Anchored = true
	seat.HeadsUpDisplay = false
	seat.Parent = model
	table.insert(parts, seat)

	local prompt = Instance.new("ProximityPrompt")
	prompt.ActionText = "Drive"
	prompt.ObjectText = "Car"
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
	linear.MaxForce = 80000
	linear.Parent = root

	-- Also holds pitch/roll at zero, which keeps the car from tipping over.
	local angular = Instance.new("AngularVelocity")
	angular.Name = "Steer"
	angular.Attachment0 = attachment
	angular.RelativeTo = Enum.ActuatorRelativeTo.World
	angular.AngularVelocity = Vector3.new(0, 0, 0)
	angular.MaxTorque = 80000
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
	}
end

local carsByPlayer = {}
local activeCars = {}
local lastSpawn = {}

local function moveToward(value, target, maxDelta)
	if value < target then
		return math.min(value + maxDelta, target)
	end
	return math.max(value - maxDelta, target)
end

local function removeCar(player)
	local car = carsByPlayer[player]
	if car then
		activeCars[car] = nil
		car.model:Destroy()
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

	local candidates = { look * 14, right * 10, -right * 10, -look * 14 }
	for _, offset in ipairs(candidates) do
		local origin = hrp.Position + offset + Vector3.new(0, 30, 0)
		local result = Workspace:Raycast(origin, Vector3.new(0, -80, 0), params)
		if result and math.abs(result.Position.Y - feetY) < 4 then
			local pos = Vector3.new(origin.X, result.Position.Y + 0.6, origin.Z)
			return CFrame.lookAt(pos, pos + look)
		end
	end

	local fallback = Vector3.new(hrp.Position.X, feetY + 0.6, hrp.Position.Z) + look * 8
	return CFrame.lookAt(fallback, fallback + look)
end

local function spawnCarFor(player)
	local character = player.Character
	if not character then
		return
	end
	local cframe = findSpawnCFrame(character)
	if not cframe then
		return
	end

	removeCar(player)
	local ok, car = pcall(buildCar, cframe)
	if not ok then
		warn("[TiranaCars] Building the car failed: " .. tostring(car))
		return
	end
	carsByPlayer[player] = car
	activeCars[car] = true
	pcall(function()
		car.root:SetNetworkOwner(nil)
	end)

	car.prompt.Triggered:Connect(function(who)
		local whoCharacter = who.Character
		local humanoid = whoCharacter and whoCharacter:FindFirstChildOfClass("Humanoid")
		if humanoid and not car.seat.Occupant then
			car.seat:Sit(humanoid)
		end
	end)
	car.seat:GetPropertyChangedSignal("Occupant"):Connect(function()
		car.prompt.Enabled = car.seat.Occupant == nil
	end)
	print("[TiranaCars] Spawned a car for " .. player.Name)
end

spawnEvent.OnServerEvent:Connect(function(player)
	local now = os.clock()
	if lastSpawn[player] and now - lastSpawn[player] < SPAWN_COOLDOWN then
		return
	end
	lastSpawn[player] = now
	spawnCarFor(player)
end)

local function onPlayerAdded(player)
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
	removeCar(player)
	lastSpawn[player] = nil
end)

RunService.Heartbeat:Connect(function(dt)
	for car in pairs(activeCars) do
		if not car.root.Parent or car.root.Position.Y < -100 then
			activeCars[car] = nil
			if car.model.Parent then
				car.model:Destroy()
			end
		else
			local occupied = car.seat.Occupant ~= nil
			local throttle = occupied and car.seat.ThrottleFloat or 0
			local steer = occupied and car.seat.SteerFloat or 0

			local target = throttle >= 0 and throttle * MAX_SPEED or throttle * MAX_REVERSE
			local rate
			if car.speed ~= 0 and target ~= 0 and (target > 0) ~= (car.speed > 0) then
				rate = BRAKING
			elseif math.abs(target) > math.abs(car.speed) then
				rate = ACCELERATION
			else
				rate = COASTING
			end
			car.speed = moveToward(car.speed, target, rate * dt)

			-- Steering only works while moving, and flips when reversing.
			-- Positive yaw turns left, so D (+1) negates it.
			local turnFactor = math.clamp(math.abs(car.speed) / 12, 0, 1)
			local direction = car.speed >= 0 and 1 or -1
			car.angular.AngularVelocity = Vector3.new(0, -steer * TURN_RATE * turnFactor * direction, 0)

			local forward = car.root.CFrame.LookVector
			local flat = Vector3.new(forward.X, 0, forward.Z)
			if flat.Magnitude > 0.01 then
				flat = flat.Unit * car.speed
			end
			car.linear.PlaneVelocity = Vector2.new(flat.X, flat.Z)
		end
	end
end)

print("[TiranaCars] Car system ready.")

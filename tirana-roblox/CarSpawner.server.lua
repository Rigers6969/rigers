--[[
	CarSpawner - Script in ServerScriptService (sibling of CarBuilder).

	- Spawns a car in front of a player when their "Spawn Car" button
	  (SpawnCarButton.client.lua) fires the SpawnTiranaCar RemoteEvent.
	  One car per player: spawning again replaces the old one.
	- Walk up to a car and press E ("Drive"), or just touch the seat.
	- W/S (or gamepad triggers) = gas/brake/reverse, A/D = steer,
	  Space = get out.
	- Drives every car from one Heartbeat loop, reading each seat's input.
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
local TURN_RATE = math.rad(90) -- degrees/second at full steer and speed
local SPAWN_COOLDOWN = 2

-- Created before anything that could fail, so the Spawn Car button can
-- always reach the server and report a problem instead of hanging.
local spawnEvent = ReplicatedStorage:FindFirstChild("SpawnTiranaCar")
if not spawnEvent then
	spawnEvent = Instance.new("RemoteEvent")
	spawnEvent.Name = "SpawnTiranaCar"
	spawnEvent.Parent = ReplicatedStorage
end

local builderModule = script.Parent:WaitForChild("CarBuilder", 10)
local CarBuilder = nil
if builderModule and builderModule:IsA("ModuleScript") then
	local ok, result = pcall(require, builderModule)
	if ok then
		CarBuilder = result
	else
		warn("[TiranaCars] CarBuilder has an error: " .. tostring(result))
	end
else
	warn("[TiranaCars] No ModuleScript named exactly 'CarBuilder' next to CarSpawner in " .. script.Parent:GetFullName())
end
if CarBuilder then
	print("[TiranaCars] Car system ready - press C in game to spawn a car.")
end

local carsFolder = Workspace:FindFirstChild("TiranaCars")
if not carsFolder then
	carsFolder = Instance.new("Folder")
	carsFolder.Name = "TiranaCars"
	carsFolder.Parent = Workspace
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
-- ground is at street level - so the car doesn't land on a rooftop or
-- inside a building.
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

local function onSeatTriggered(car, who)
	local character = who.Character
	local humanoid = character and character:FindFirstChildOfClass("Humanoid")
	if humanoid and not car.seat.Occupant then
		car.seat:Sit(humanoid)
	end
end

spawnEvent.OnServerEvent:Connect(function(player)
	if not CarBuilder then
		warn("[TiranaCars] Can't spawn a car - CarBuilder isn't set up (see the warning above).")
		return
	end
	local now = os.clock()
	if lastSpawn[player] and now - lastSpawn[player] < SPAWN_COOLDOWN then
		return
	end
	lastSpawn[player] = now

	local character = player.Character
	if not character then
		return
	end
	local cframe = findSpawnCFrame(character)
	if not cframe then
		return
	end

	removeCar(player)
	local car = CarBuilder.Build(cframe, carsFolder)
	carsByPlayer[player] = car
	activeCars[car] = true
	pcall(function()
		car.root:SetNetworkOwner(nil)
	end)

	car.prompt.Triggered:Connect(function(who)
		onSeatTriggered(car, who)
	end)
	car.seat:GetPropertyChangedSignal("Occupant"):Connect(function()
		car.prompt.Enabled = car.seat.Occupant == nil
	end)
end)

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

			-- Steering only works while moving, and flips when reversing,
			-- like a real car. Positive yaw turns left, so D (+1) negates it.
			local turnFactor = math.clamp(math.abs(car.speed) / 12, 0, 1)
			local direction = car.speed >= 0 and 1 or -1
			local yawRate = -steer * TURN_RATE * turnFactor * direction
			car.angular.AngularVelocity = Vector3.new(0, yawRate, 0)

			local forward = car.root.CFrame.LookVector
			local flat = Vector3.new(forward.X, 0, forward.Z)
			if flat.Magnitude > 0.01 then
				flat = flat.Unit * car.speed
			end
			car.linear.PlaneVelocity = Vector2.new(flat.X, flat.Z)
		end
	end
end)

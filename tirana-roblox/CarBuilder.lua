--[[
	CarBuilder - ModuleScript (put it in ServerScriptService, next to
	CarSpawner). Builds a proper-looking car out of parts: painted body,
	tinted cabin with sloped windshield/rear window, roof, bumpers,
	grille, headlights, taillights, and four wheels with rims.

	Driving is arcade-style: an invisible "Root" box underneath carries
	the physics, pushed by a LinearVelocity (drive) and AngularVelocity
	(steering) that CarSpawner updates every frame from the seat's input.
	That's far steadier than wheel-joint physics - it can't flip, jitter
	or get stuck on kerbs - at the cost of the wheels being cosmetic.

	The car's front is the model's -Z side (Roblox's LookVector), so
	CFrame.lookAt(position, position + direction) points it that way.
]]

local CarBuilder = {}

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

-- Builds the car at `rootCFrame` (the center of the invisible physics
-- box, which should sit ~0.5 studs above the ground) and parents it to
-- `parent`. Returns a table with the pieces CarSpawner needs.
function CarBuilder.Build(rootCFrame, parent, paintColor)
	local rng = Random.new()
	local paint = paintColor or PAINT_COLORS[rng:NextInteger(1, #PAINT_COLORS)]

	local model = Instance.new("Model")
	model.Name = "Car"

	local root = Instance.new("Part")
	root.Name = "Root"
	root.Size = Vector3.new(6, 1, 12)
	root.CFrame = rootCFrame
	root.Transparency = 1
	root.CanCollide = true
	root.Anchored = true
	-- Low friction so the velocity movers glide it smoothly instead of
	-- fighting ground friction every frame.
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

	-- Body
	local body = add("Part", "Body", Vector3.new(6.2, 1.9, 12.8), CFrame.new(0, 1.45, 0), paint, Enum.Material.SmoothPlastic)
	body.Reflectance = 0.1

	-- Cabin + glass. A WedgePart's full height is at its +Z side and it
	-- slopes down to -Z, so an unrotated wedge in front of the cabin reads
	-- as a windshield; the rear one is turned 180 degrees.
	local cabin = add("Part", "Cabin", Vector3.new(5.6, 1.9, 6), CFrame.new(0, 3.35, 0.9), GLASS_COLOR, Enum.Material.Glass)
	cabin.Transparency = 0.25
	local windshield = add("WedgePart", "Windshield", Vector3.new(5.6, 1.9, 1.8), CFrame.new(0, 3.35, -3), GLASS_COLOR, Enum.Material.Glass)
	windshield.Transparency = 0.25
	local rearWindow = add("WedgePart", "RearWindow", Vector3.new(5.6, 1.9, 1.8), CFrame.new(0, 3.35, 4.8) * CFrame.Angles(0, math.pi, 0), GLASS_COLOR, Enum.Material.Glass)
	rearWindow.Transparency = 0.25
	add("Part", "Roof", Vector3.new(5.8, 0.3, 5.4), CFrame.new(0, 4.45, 1), paint, Enum.Material.SmoothPlastic)

	-- Front/back details
	add("Part", "FrontBumper", Vector3.new(6.4, 0.6, 0.5), CFrame.new(0, 1, -6.55), TRIM_COLOR, Enum.Material.SmoothPlastic)
	add("Part", "RearBumper", Vector3.new(6.4, 0.6, 0.5), CFrame.new(0, 1, 6.55), TRIM_COLOR, Enum.Material.SmoothPlastic)
	add("Part", "Grille", Vector3.new(2.4, 0.6, 0.12), CFrame.new(0, 1.9, -6.45), TRIM_COLOR, Enum.Material.Metal)
	for _, x in ipairs({ -2.2, 2.2 }) do
		add("Part", "Headlight", Vector3.new(1.3, 0.5, 0.15), CFrame.new(x, 2, -6.45), Color3.fromRGB(255, 244, 214), Enum.Material.Neon)
		add("Part", "Taillight", Vector3.new(1.3, 0.5, 0.15), CFrame.new(x, 2, 6.45), Color3.fromRGB(210, 20, 20), Enum.Material.Neon)
	end

	-- Wheels: a Cylinder's round faces are on its local X axis, which is
	-- already the car's side-to-side axis, so no rotation is needed.
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
	-- in the workspace yet is the classic way to end up with a car that
	-- falls apart on spawn.
	model.Parent = parent
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

	-- Also holds pitch/roll rotation at zero, which is what keeps the car
	-- from ever tipping over.
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

return CarBuilder

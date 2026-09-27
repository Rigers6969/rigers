--[[
	SpawnCarButton - LocalScript in StarterPlayer > StarterPlayerScripts.
	Draws the dealership: G (or the "Dealership" button) opens the list of
	every car with its price and real specs - buy it, or spawn one you own.
	C respawns your current car. Your cash shows at the top of the list
	and in the player list (top right).
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")

local player = Players.LocalPlayer

local BLUE = Color3.fromRGB(38, 110, 220)
local GREEN = Color3.fromRGB(40, 160, 80)
local GREY = Color3.fromRGB(90, 90, 98)
local RED = Color3.fromRGB(200, 60, 50)
local PANEL = Color3.fromRGB(24, 26, 32)
local ROW = Color3.fromRGB(38, 41, 50)
local GOLD = Color3.fromRGB(201, 162, 75)

local function formatMoney(n)
	local s = tostring(math.floor(n))
	local formatted = s
	while true do
		local replaced
		formatted, replaced = string.gsub(formatted, "^(-?%d+)(%d%d%d)", "%1,%2")
		if replaced == 0 then
			break
		end
	end
	return "$" .. formatted
end

local function corner(parent, radius)
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, radius or 8)
	c.Parent = parent
end

local function makeButton(parent, text, color)
	local b = Instance.new("TextButton")
	b.BackgroundColor3 = color
	b.TextColor3 = Color3.fromRGB(255, 255, 255)
	b.Font = Enum.Font.GothamBold
	b.TextSize = 15
	b.Text = text
	b.AutoButtonColor = true
	b.Parent = parent
	corner(b)
	return b
end

local gui = Instance.new("ScreenGui")
gui.Name = "TiranaCarGui"
gui.ResetOnSpawn = false
gui.Parent = player:WaitForChild("PlayerGui")

local dealershipButton = makeButton(gui, "Dealership (G)", GOLD)
dealershipButton.Size = UDim2.new(0, 200, 0, 44)
dealershipButton.AnchorPoint = Vector2.new(1, 0)
dealershipButton.Position = UDim2.new(1, -20, 0, 240)

local spawnButton = makeButton(gui, "Spawn My Car (C)", BLUE)
spawnButton.Size = UDim2.new(0, 200, 0, 44)
spawnButton.AnchorPoint = Vector2.new(1, 0)
spawnButton.Position = UDim2.new(1, -20, 0, 292)

local panel = Instance.new("Frame")
panel.Size = UDim2.new(0, 620, 0, 460)
panel.AnchorPoint = Vector2.new(0.5, 0.5)
panel.Position = UDim2.new(0.5, 0, 0.5, 0)
panel.BackgroundColor3 = PANEL
panel.Visible = false
panel.Parent = gui
corner(panel, 12)

local title = Instance.new("TextLabel")
title.Size = UDim2.new(1, -120, 0, 44)
title.Position = UDim2.new(0, 16, 0, 8)
title.BackgroundTransparency = 1
title.TextXAlignment = Enum.TextXAlignment.Left
title.Font = Enum.Font.GothamBold
title.TextSize = 22
title.TextColor3 = GOLD
title.Text = "Tirana Auto - Dealership"
title.Parent = panel

local closeButton = makeButton(panel, "X", RED)
closeButton.Size = UDim2.new(0, 36, 0, 36)
closeButton.Position = UDim2.new(1, -48, 0, 12)

local cashLabel = Instance.new("TextLabel")
cashLabel.Size = UDim2.new(1, -32, 0, 22)
cashLabel.Position = UDim2.new(0, 16, 0, 50)
cashLabel.BackgroundTransparency = 1
cashLabel.TextXAlignment = Enum.TextXAlignment.Left
cashLabel.Font = Enum.Font.Gotham
cashLabel.TextSize = 16
cashLabel.TextColor3 = Color3.fromRGB(220, 220, 225)
cashLabel.Text = "Cash: ..."
cashLabel.Parent = panel

local messageLabel = Instance.new("TextLabel")
messageLabel.Size = UDim2.new(1, -32, 0, 20)
messageLabel.Position = UDim2.new(0, 16, 1, -28)
messageLabel.BackgroundTransparency = 1
messageLabel.TextXAlignment = Enum.TextXAlignment.Left
messageLabel.Font = Enum.Font.Gotham
messageLabel.TextSize = 14
messageLabel.TextColor3 = Color3.fromRGB(255, 220, 120)
messageLabel.Text = ""
messageLabel.Parent = panel

local list = Instance.new("ScrollingFrame")
list.Size = UDim2.new(1, -32, 1, -118)
list.Position = UDim2.new(0, 16, 0, 80)
list.BackgroundTransparency = 1
list.BorderSizePixel = 0
list.ScrollBarThickness = 8
list.AutomaticCanvasSize = Enum.AutomaticSize.Y
list.CanvasSize = UDim2.new(0, 0, 0, 0)
list.Parent = panel

local layout = Instance.new("UIListLayout")
layout.Padding = UDim.new(0, 6)
layout.SortOrder = Enum.SortOrder.LayoutOrder
layout.Parent = list

local function getShop()
	return ReplicatedStorage:FindFirstChild("TiranaCarShop")
end

local function getSpawnEvent()
	return ReplicatedStorage:FindFirstChild("SpawnTiranaCar")
end

local function showMessage(text)
	messageLabel.Text = text or ""
end

local function updateCash()
	local stats = player:FindFirstChild("leaderstats")
	local cash = stats and stats:FindFirstChild("Cash")
	cashLabel.Text = cash and ("Cash: " .. formatMoney(cash.Value)) or "Cash: ..."
end

local function spawnCar(carId)
	local event = getSpawnEvent()
	if not event then
		showMessage("Car server script missing - CarSpawner must be a Script in ServerScriptService.")
		return
	end
	event:FireServer(carId)
end

local renderList

local function buy(carId)
	local shop = getShop()
	if not shop then
		showMessage("Car server script missing - CarSpawner must be a Script in ServerScriptService.")
		return
	end
	local ok, result = pcall(function()
		return shop:InvokeServer("buy", carId)
	end)
	if not ok or type(result) ~= "table" then
		showMessage("Purchase failed - try again.")
		return
	end
	showMessage(result.message)
	if result.catalog then
		renderList(result.catalog, false)
	end
end

renderList = function(catalog, free)
	for _, child in ipairs(list:GetChildren()) do
		if child:IsA("Frame") then
			child:Destroy()
		end
	end
	for index, car in ipairs(catalog) do
		local row = Instance.new("Frame")
		row.Size = UDim2.new(1, -12, 0, 58)
		row.BackgroundColor3 = ROW
		row.LayoutOrder = index
		row.Parent = list
		corner(row)

		local name = Instance.new("TextLabel")
		name.Size = UDim2.new(1, -170, 0, 26)
		name.Position = UDim2.new(0, 12, 0, 6)
		name.BackgroundTransparency = 1
		name.TextXAlignment = Enum.TextXAlignment.Left
		name.Font = Enum.Font.GothamBold
		name.TextSize = 16
		name.TextColor3 = Color3.fromRGB(255, 255, 255)
		name.TextTruncate = Enum.TextTruncate.AtEnd
		name.Text = car.name
		name.Parent = row

		local specs = Instance.new("TextLabel")
		specs.Size = UDim2.new(1, -170, 0, 20)
		specs.Position = UDim2.new(0, 12, 0, 32)
		specs.BackgroundTransparency = 1
		specs.TextXAlignment = Enum.TextXAlignment.Left
		specs.Font = Enum.Font.Gotham
		specs.TextSize = 13
		specs.TextColor3 = Color3.fromRGB(170, 175, 185)
		specs.Text = string.format("%s  |  %d km/h  |  0-100 in %.1fs  |  %s", formatMoney(car.price), car.topSpeed, car.zeroTo100,
			car.hasModel and "3D model" or ("block body - model id: " .. car.id))
		specs.Parent = row

		local actionButton
		if car.owned then
			actionButton = makeButton(row, "Spawn", GREEN)
			actionButton.Activated:Connect(function()
				spawnCar(car.id)
				panel.Visible = false
			end)
		else
			actionButton = makeButton(row, "Buy " .. formatMoney(car.price), BLUE)
			actionButton.Activated:Connect(function()
				buy(car.id)
			end)
		end
		actionButton.Size = UDim2.new(0, 140, 0, 38)
		actionButton.AnchorPoint = Vector2.new(1, 0.5)
		actionButton.Position = UDim2.new(1, -10, 0.5, 0)
		actionButton.TextSize = 14
	end
	if free then
		showMessage("Studio test mode: every car is free.")
	end
end

local function openDealership()
	local shop = getShop()
	if not shop then
		panel.Visible = true
		showMessage("Car server script missing - CarSpawner must be a Script in ServerScriptService.")
		return
	end
	panel.Visible = true
	updateCash()
	showMessage("Loading...")
	local ok, result = pcall(function()
		return shop:InvokeServer("state")
	end)
	if ok and type(result) == "table" and result.catalog then
		showMessage("")
		renderList(result.catalog, result.free)
	else
		showMessage("Couldn't load the dealership - try again.")
	end
end

dealershipButton.Activated:Connect(function()
	if panel.Visible then
		panel.Visible = false
	else
		openDealership()
	end
end)
closeButton.Activated:Connect(function()
	panel.Visible = false
end)
spawnButton.Activated:Connect(function()
	spawnCar(nil)
end)

---------------------------------------------------------------------
-- Inside view: V while driving switches to first person from the
-- driver's seat (zoom locked all the way in), V again switches back.
---------------------------------------------------------------------

local viewHint = Instance.new("TextLabel")
viewHint.Size = UDim2.new(0, 320, 0, 32)
viewHint.AnchorPoint = Vector2.new(0.5, 1)
viewHint.Position = UDim2.new(0.5, 0, 1, -24)
viewHint.BackgroundColor3 = PANEL
viewHint.BackgroundTransparency = 0.25
viewHint.TextColor3 = Color3.fromRGB(255, 255, 255)
viewHint.Font = Enum.Font.GothamBold
viewHint.TextSize = 15
viewHint.Text = "V - inside view   |   Space - get out"
viewHint.Visible = false
viewHint.Parent = gui
corner(viewHint)

local insideView = false
local savedMinZoom, savedMaxZoom = nil, nil

local function setInsideView(on)
	if on == insideView then
		return
	end
	insideView = on
	if on then
		savedMinZoom, savedMaxZoom = player.CameraMinZoomDistance, player.CameraMaxZoomDistance
		player.CameraMaxZoomDistance = 0.5
		player.CameraMinZoomDistance = 0.5
		viewHint.Text = "V - outside view   |   Space - get out"
	else
		player.CameraMaxZoomDistance = savedMaxZoom or 128
		player.CameraMinZoomDistance = savedMinZoom or 0.5
		viewHint.Text = "V - inside view   |   Space - get out"
	end
end

local function drivingSeat()
	local character = player.Character
	local humanoid = character and character:FindFirstChildOfClass("Humanoid")
	local seat = humanoid and humanoid.SeatPart
	if seat and seat:IsA("VehicleSeat") then
		return seat
	end
	return nil
end

local function onCharacter(character)
	local humanoid = character:WaitForChild("Humanoid", 10)
	if not humanoid then
		return
	end
	humanoid:GetPropertyChangedSignal("SeatPart"):Connect(function()
		local driving = drivingSeat() ~= nil
		viewHint.Visible = driving
		if not driving then
			setInsideView(false)
		end
	end)
end

player.CharacterAdded:Connect(function(character)
	setInsideView(false)
	viewHint.Visible = false
	onCharacter(character)
end)
if player.Character then
	task.spawn(onCharacter, player.Character)
end

UserInputService.InputBegan:Connect(function(input, gameProcessed)
	if gameProcessed then
		return
	end
	if input.KeyCode == Enum.KeyCode.V then
		if drivingSeat() then
			setInsideView(not insideView)
		end
	elseif input.KeyCode == Enum.KeyCode.G then
		if panel.Visible then
			panel.Visible = false
		else
			openDealership()
		end
	elseif input.KeyCode == Enum.KeyCode.C then
		spawnCar(nil)
	end
end)

-- Keep the cash line live while the dealership is open.
task.spawn(function()
	local stats = player:WaitForChild("leaderstats", 30)
	local cash = stats and stats:WaitForChild("Cash", 10)
	if cash then
		cash.Changed:Connect(updateCash)
		updateCash()
	end
end)

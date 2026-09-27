--[[
	SpawnCarButton - LocalScript in StarterPlayer > StarterPlayerScripts.
	Adds a "Spawn Car (C)" button (and the C key) that asks CarSpawner for
	a car. The button always appears right away; if the server-side car
	script isn't found, the button itself says so instead of doing nothing.
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")

local player = Players.LocalPlayer

local gui = Instance.new("ScreenGui")
gui.Name = "TiranaCarGui"
gui.ResetOnSpawn = false
gui.Parent = player:WaitForChild("PlayerGui")

local button = Instance.new("TextButton")
button.Name = "SpawnCar"
button.Size = UDim2.new(0, 200, 0, 44)
button.AnchorPoint = Vector2.new(1, 0)
button.Position = UDim2.new(1, -20, 0, 240)
button.BackgroundColor3 = Color3.fromRGB(38, 110, 220)
button.TextColor3 = Color3.fromRGB(255, 255, 255)
button.Font = Enum.Font.GothamBold
button.TextSize = 16
button.TextWrapped = true
button.Text = "Spawn Car (C)"
button.AutoButtonColor = true
button.Parent = gui

local corner = Instance.new("UICorner")
corner.CornerRadius = UDim.new(0, 8)
corner.Parent = button

local function requestCar()
	local spawnEvent = ReplicatedStorage:FindFirstChild("SpawnTiranaCar")
	if not spawnEvent then
		button.Text = "Car server script missing - check CarSpawner"
		button.BackgroundColor3 = Color3.fromRGB(200, 60, 50)
		warn("[TiranaCars] No 'SpawnTiranaCar' RemoteEvent - CarSpawner isn't running. It must be a Script (not LocalScript/ModuleScript) in ServerScriptService.")
		return
	end
	button.Text = "Spawn Car (C)"
	button.BackgroundColor3 = Color3.fromRGB(38, 110, 220)
	spawnEvent:FireServer()
end

button.Activated:Connect(requestCar)

UserInputService.InputBegan:Connect(function(input, gameProcessed)
	if not gameProcessed and input.KeyCode == Enum.KeyCode.C then
		requestCar()
	end
end)

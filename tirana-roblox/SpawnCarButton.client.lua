--[[
	SpawnCarButton - LocalScript in StarterPlayer > StarterPlayerScripts.
	Adds a "Spawn Car" button (and the C key) that asks CarSpawner for a car.
]]

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local UserInputService = game:GetService("UserInputService")

local player = Players.LocalPlayer
local spawnEvent = ReplicatedStorage:WaitForChild("SpawnTiranaCar")

local gui = Instance.new("ScreenGui")
gui.Name = "TiranaCarGui"
gui.ResetOnSpawn = false
gui.Parent = player:WaitForChild("PlayerGui")

local button = Instance.new("TextButton")
button.Name = "SpawnCar"
button.Size = UDim2.new(0, 160, 0, 44)
button.AnchorPoint = Vector2.new(1, 0)
button.Position = UDim2.new(1, -20, 0, 90)
button.BackgroundColor3 = Color3.fromRGB(38, 110, 220)
button.TextColor3 = Color3.fromRGB(255, 255, 255)
button.Font = Enum.Font.GothamBold
button.TextSize = 16
button.Text = "Spawn Car (C)"
button.AutoButtonColor = true
button.Parent = gui

local corner = Instance.new("UICorner")
corner.CornerRadius = UDim.new(0, 8)
corner.Parent = button

local function requestCar()
	spawnEvent:FireServer()
end

button.Activated:Connect(requestCar)

UserInputService.InputBegan:Connect(function(input, gameProcessed)
	if not gameProcessed and input.KeyCode == Enum.KeyCode.C then
		requestCar()
	end
end)

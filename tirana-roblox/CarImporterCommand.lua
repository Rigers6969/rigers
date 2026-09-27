--[[
	CarImporterCommand - paste this WHOLE file into Studio's command box
	(the code box at the bottom of Studio with the "Run" button) and click
	Run. Not during Play. It does exactly what CarImporter.lua does -
	searches the free models for every dealership car, strips all scripts
	from them, and files them under ServerStorage > CarModels with the
	right names - just without needing a ModuleScript. Watch progress in
	the Output panel (Window -> Output). SAVE the place afterwards.

	Generated from CarImporter.lua - edit that file, not this one.
]]

print("[CarImporter] Starting - this can take a minute or two...")

local InsertService = game:GetService("InsertService")
local ServerStorage = game:GetService("ServerStorage")

-- id (must match CarSpawner's catalog), search text, words that must
-- appear in the model's name for it to count as a match.
local CARS = {
	{ "mercedes190e", "Mercedes 190E", { "190" } },
	{ "sandero", "Dacia Sandero", { "sandero" } },
	{ "corolla", "Toyota Corolla", { "corolla" } },
	{ "civic", "Honda Civic", { "civic" } },
	{ "golfgti", "Volkswagen Golf GTI", { "golf" } },
	{ "mustang", "Ford Mustang", { "mustang" } },
	{ "cclass", "Mercedes C Class", { "c class", "c-class", "c63", "c300", "c200" } },
	{ "bmwm3", "BMW M3", { "m3" } },
	{ "teslaplaid", "Tesla Model S", { "model s", "tesla" } },
	{ "rangerover", "Range Rover", { "range rover", "rangerover" } },
	{ "porsche911", "Porsche 911", { "911" } },
	{ "g63", "Mercedes G63", { "g63", "g wagon", "g-wagon", "gwagon", "g class", "g-class" } },
	{ "urus", "Lamborghini Urus", { "urus" } },
	{ "ferrari296", "Ferrari 296 GTB", { "296" } },
	{ "cullinan", "Rolls Royce Cullinan", { "cullinan" } },
	{ "mclaren765", "McLaren 765LT", { "765" } },
	{ "phantom", "Rolls Royce Phantom", { "phantom" } },
	{ "revuelto", "Lamborghini Revuelto", { "revuelto" } },
	{ "senna", "McLaren Senna", { "senna" } },
	{ "laferrari", "Ferrari LaFerrari", { "laferrari", "la ferrari" } },
	{ "huayra", "Pagani Huayra", { "huayra" } },
	{ "chiron", "Bugatti Chiron", { "chiron" } },
	{ "jesko", "Koenigsegg Jesko", { "jesko" } },
	{ "divo", "Bugatti Divo", { "divo" } },
	{ "centodieci", "Bugatti Centodieci", { "centodieci", "110" } },
}

local MIN_PARTS = 8 -- fewer than this is almost certainly not a car
local DEFAULT_MAX_PARTS = 1500 -- more than this lags badly with several cars out
local CANDIDATES_PER_CAR = 10

local function searchFreeModels(text)
	local ok, pages = pcall(function()
		return InsertService:GetFreeModelsAsync(text, 0)
	end)
	if not ok then
		-- Older Studio builds only have the pre-"Async" name.
		ok, pages = pcall(function()
			return InsertService:GetFreeModels(text, 0)
		end)
	end
	if not ok or type(pages) ~= "table" or type(pages[1]) ~= "table" then
		return nil, tostring(pages)
	end
	return pages[1].Results or {}
end

-- Loads an asset as a single Model, or returns nil.
local function loadModel(assetId)
	local ok, objects = pcall(function()
		return game:GetObjects("rbxassetid://" .. tostring(assetId))
	end)
	if not ok or type(objects) ~= "table" or #objects == 0 then
		local loaded
		ok, loaded = pcall(function()
			return InsertService:LoadAsset(assetId)
		end)
		if not ok or not loaded then
			return nil
		end
		objects = loaded:GetChildren()
	end

	if #objects == 1 and objects[1]:IsA("Model") then
		return objects[1]
	end
	local model = Instance.new("Model")
	for _, object in ipairs(objects) do
		object.Parent = model
	end
	return model
end

local function stripScripts(model)
	local removed = 0
	for _, descendant in ipairs(model:GetDescendants()) do
		if descendant:IsA("LuaSourceContainer") then
			descendant:Destroy()
			removed = removed + 1
		end
	end
	return removed
end

local function countParts(model)
	local count = 0
	for _, descendant in ipairs(model:GetDescendants()) do
		if descendant:IsA("BasePart") then
			count = count + 1
		end
	end
	return count
end

local function nameMatches(name, keywords)
	local lower = string.lower(name or "")
	for _, word in ipairs(keywords) do
		if string.find(lower, word, 1, true) then
			return true
		end
	end
	return false
end

-- Returns (model, result item, matchedByName) or nil.
local function findModelFor(car, maxParts, skip)
	local results, err = searchFreeModels(car[2])
	if not results then
		warn("[CarImporter] Search failed for " .. car[2] .. ": " .. tostring(err))
		return nil
	end

	-- Name matches first, then everything else as a fallback.
	local ordered = {}
	for _, item in ipairs(results) do
		if nameMatches(item.Name, car[3]) then
			table.insert(ordered, { item = item, matched = true })
		end
	end
	for _, item in ipairs(results) do
		if not nameMatches(item.Name, car[3]) then
			table.insert(ordered, { item = item, matched = false })
		end
	end

	local accepted = 0
	for index, entry in ipairs(ordered) do
		if index > CANDIDATES_PER_CAR then
			break
		end
		local model = loadModel(entry.item.AssetId)
		if model then
			stripScripts(model)
			local parts = countParts(model)
			if parts >= MIN_PARTS and parts <= maxParts then
				if accepted >= skip then
					return model, entry.item, entry.matched, parts
				end
				accepted = accepted + 1
			end
			model:Destroy()
		end
	end
	return nil
end

local function run(options)
	options = options or {}
	local maxParts = options.maxParts or DEFAULT_MAX_PARTS
	local skip = options.skip or 0
	local only = nil
	if type(options.only) == "table" then
		only = {}
		for _, id in ipairs(options.only) do
			only[id] = true
		end
	end

	local folder = ServerStorage:FindFirstChild("CarModels")
	if not folder then
		folder = Instance.new("Folder")
		folder.Name = "CarModels"
		folder.Parent = ServerStorage
	end

	local imported, skippedExisting, notFound, checkMe = 0, 0, {}, {}
	for _, car in ipairs(CARS) do
		local id = car[1]
		if not only or only[id] then
			local existing = folder:FindFirstChild(id)
			if existing and not options.replace then
				skippedExisting = skippedExisting + 1
			else
				print("[CarImporter] Searching: " .. car[2] .. " ...")
				local model, item, matched, parts = findModelFor(car, maxParts, skip)
				if model then
					if existing then
						existing:Destroy()
					end
					model.Name = id
					model:SetAttribute("SourceAssetId", item.AssetId)
					model:SetAttribute("SourceName", item.Name)
					model:SetAttribute("SourceCreator", item.CreatorName)
					if not matched then
						model:SetAttribute("CheckMe", true)
						table.insert(checkMe, id)
					end
					model.Parent = folder
					imported = imported + 1
					print(string.format("[CarImporter]   -> %s: \"%s\" by %s (%d parts)%s", id, tostring(item.Name), tostring(item.CreatorName), parts, matched and "" or "  <- name didn't match, check it"))
				else
					table.insert(notFound, id)
					warn("[CarImporter]   -> nothing usable found for " .. car[2])
				end
			end
		end
	end

	print(string.format("[CarImporter] Done: %d imported, %d already there (use replace = true to redo), %d not found.", imported, skippedExisting, #notFound))
	if #checkMe > 0 then
		warn("[CarImporter] Picked without a name match - check these look right: " .. table.concat(checkMe, ", "))
	end
	if #notFound > 0 then
		warn("[CarImporter] Add these by hand from the Toolbox (rename to the id, drop in CarModels): " .. table.concat(notFound, ", "))
	end
	print("[CarImporter] Now SAVE the place (File -> Save) so the models are kept.")
end

run()

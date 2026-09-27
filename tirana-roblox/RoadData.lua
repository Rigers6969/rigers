--[[
	RoadData.lua - a ModuleScript holding central Tirana's real street
	layout: real street names and landmarks, placed in their correct
	relative geographic arrangement, but hand-authored from general
	knowledge of the city rather than pulled from a live mapping API
	(this dev sandbox has no outbound access to OpenStreetMap/Overpass -
	see the repo's README). Treat this as "recognizable layout", not
	survey-precise coordinates.

	Scale: 1 stud = 1 meter (a common convention for Roblox driving
	games - keeps car/building sizes sane without extra scaling math).
	Axes: +X = East, -X = West, +Z = South, -Z = North. Skanderbeg
	Square (the real city center) sits at the origin, (0, 0).

	Each road is a polyline through `points` ({x, z} pairs, in studs).
	RoadBuilder.server.lua turns each consecutive pair of points into
	one flat Part. `width` is in studs. Roads that should connect for
	traffic AI share an exact endpoint coordinate with another road.
]]

return {
	Roads = {
		{
			name = "Bulevardi Dëshmorët e Kombit",
			description = "The city's main north-south boulevard, running through Skanderbeg Square.",
			type = "boulevard",
			width = 24,
			points = { {0, -650}, {0, 0}, {0, 700}, {0, 1400} },
		},
		{
			name = "Rruga e Kavajës",
			description = "Major artery heading west out of the center, towards Kavajë / the Kashar-Rinas direction. Extended further out than the tight city center - treat the outer stretch as approximate corridor direction, not a precise trace.",
			type = "primary",
			width = 16,
			points = { {-50, 50}, {-700, 150}, {-1500, 250}, {-2200, 320} },
		},
		{
			name = "Rruga e Durrësit",
			description = "Major artery heading northwest out of the center, towards Durrës, passing the Kombinat/Laprakë area and on towards Kamëz. Outer stretch is approximate corridor direction, not a precise trace.",
			type = "primary",
			width = 16,
			points = { {-50, -100}, {-700, -600}, {-1400, -1100}, {-2100, -1700} },
		},
		{
			name = "Rruga e Elbasanit",
			description = "Major artery heading east/southeast out of the center, towards Elbasan, passing the Selitë/Babrru area and on towards Sauk. Outer stretch is approximate corridor direction, not a precise trace.",
			type = "primary",
			width = 16,
			points = { {50, 100}, {700, 500}, {1400, 950}, {2100, 1500} },
		},
		{
			name = "Rruga e Kombinatit",
			description = "Short branch off Rruga e Durrësit into the Kombinat district (approximate placement). Starts at one of Rruga e Durrësit's own waypoints so the two roads actually connect.",
			type = "secondary",
			width = 10,
			points = { {-700, -600}, {-1050, -400} },
		},
		{
			name = "Rruga e Barrikadave",
			description = "Secondary street roughly parallel to the boulevard, connecting Kavajës to the Mother Teresa Square area. Both ends share an exact point with Kavajës / the boulevard so the network is actually connected.",
			type = "secondary",
			width = 10,
			points = { {-50, 50}, {-350, 450}, {0, 700} },
		},
		{
			name = "Blloku Connector",
			description = "Short link from Rruga e Barrikadave into the Blloku grid, so the grid isn't an isolated island for traffic AI.",
			type = "local",
			width = 7,
			points = { {-350, 450}, {-300, 500} },
		},
		{
			name = "Rruga e Kavajës - Blloku Nord",
			description = "Blloku district local street (north edge of the grid).",
			type = "local",
			width = 7,
			points = { {-300, 500}, {-100, 500} },
		},
		{
			name = "Rruga e Kavajës - Blloku Sud",
			description = "Blloku district local street (south edge of the grid).",
			type = "local",
			width = 7,
			points = { {-300, 650}, {-100, 650} },
		},
		{
			name = "Rruga Ibrahim Rugova",
			description = "Blloku district local street (west edge of the grid).",
			type = "local",
			width = 7,
			points = { {-300, 500}, {-300, 650} },
		},
		{
			name = "Rruga Sami Frashëri",
			description = "Blloku district local street (east edge of the grid).",
			type = "local",
			width = 7,
			points = { {-100, 500}, {-100, 650} },
		},
		{
			name = "Unaza (Ring Road) - West Connector",
			description = "Simplified peripheral loop for traffic AI to circulate on - schematic, not a survey-accurate trace of the real Unaza.",
			type = "ring",
			width = 14,
			points = { {-1400, -1100}, {-1500, 250} },
		},
		{
			name = "Unaza (Ring Road) - South Connector",
			description = "Simplified peripheral loop for traffic AI to circulate on - schematic, not a survey-accurate trace of the real Unaza.",
			type = "ring",
			width = 14,
			points = { {-1500, 250}, {0, 1400} },
		},
		{
			name = "Unaza (Ring Road) - Southeast Connector",
			description = "Simplified peripheral loop for traffic AI to circulate on - schematic, not a survey-accurate trace of the real Unaza.",
			type = "ring",
			width = 14,
			points = { {0, 1400}, {1400, 950} },
		},
		{
			name = "Unaza (Ring Road) - North Connector",
			description = "Simplified peripheral loop for traffic AI to circulate on - schematic, not a survey-accurate trace of the real Unaza.",
			type = "ring",
			width = 14,
			points = { {1400, 950}, {-1400, -1100} },
		},
	},

	-- Road width (studs) by type, matched to real relative proportions
	-- (a boulevard is wider than a residential street) rather than
	-- exact real measurements.
	RoadTypeColors = {
		boulevard = Color3.fromRGB(90, 90, 95),
		primary = Color3.fromRGB(80, 80, 85),
		secondary = Color3.fromRGB(75, 75, 80),
		local_ = Color3.fromRGB(70, 70, 75), -- "local" is a Lua keyword-adjacent name to avoid confusion; RoadBuilder maps type "local" to this
		ring = Color3.fromRGB(85, 85, 90),
	},

	Landmarks = {
		{ name = "Sheshi Skënderbej (Skanderbeg Square)", position = {0, 0} },
		{ name = "Sheshi Nënë Tereza (Mother Teresa Square)", position = {0, 700} },
		{ name = "Parku i Madh / Liqeni Artificial (Grand Park & Artificial Lake)", position = {0, 1400} },
		{ name = "Blloku", position = {-200, 575} },
		{ name = "Ish-Stacioni i Trenit (Old Train Station area)", position = {0, -650} },
		-- Outer districts, added along the same real corridor directions
		-- as the extended arterial roads above - approximate placement,
		-- not survey-precise (see the module docstring and README).
		{ name = "Kombinat", position = {-1050, -400} },
		{ name = "Laprakë (drejtim / direction)", position = {-1600, -1300} },
		{ name = "Kamëz (drejtim / direction)", position = {-2100, -1700} },
		{ name = "Kashar / Rinas (drejtim / direction)", position = {-2200, 320} },
		{ name = "Selitë (drejtim / direction)", position = {1400, 950} },
		{ name = "Babrru (drejtim / direction)", position = {2100, 1500} },
	},
}

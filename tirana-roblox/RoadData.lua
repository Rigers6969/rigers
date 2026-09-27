--[[
	RoadData.lua - a ModuleScript holding central Tirana's real street
	layout: real street names and landmarks, placed in their correct
	relative geographic arrangement, but hand-authored from general
	knowledge of the city rather than pulled from a live mapping API
	(this dev sandbox has no outbound access to OpenStreetMap/Overpass -
	see the repo's README). Treat this as "recognizable layout", not
	survey-precise coordinates.

	The outer districts (Babrru, Kamëz, Laprakë, Kashar, Kombinat, Sauk)
	ARE at their real positions: converted from their published
	latitude/longitude relative to Skanderbeg Square (41.3275 N,
	19.8187 E). The roads leading to them follow the right corridor but
	their exact curves are approximate, and each district's small street
	grid is a stand-in, not its real streets.

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
			description = "Major artery heading west-southwest out of the center to Kombinat (real position). The outer curve is approximate.",
			type = "primary",
			width = 16,
			points = { {-50, 50}, {-700, 150}, {-1500, 250}, {-3000, 900}, {-4327, 1484} },
		},
		{
			name = "Rruga e Durrësit",
			description = "Major artery heading northwest past Laprakë, becoming the Tirana-Durrës road out to Kashar (both at real positions). The outer curve is approximate.",
			type = "primary",
			width = 16,
			points = { {-50, -100}, {-700, -600}, {-1400, -1100}, {-2028, -1329}, {-4200, -1850}, {-8436, -2319} },
		},
		{
			name = "Rruga e Elbasanit",
			description = "Major artery heading southeast out of the center towards Sauk (real position) and Elbasan. The outer curve is approximate.",
			type = "primary",
			width = 16,
			points = { {50, 100}, {700, 500}, {1400, 950}, {1350, 2000}, {1195, 3061} },
		},
		{
			name = "Rruga për Babrru",
			description = "North from the old train station area to Babrru (real position, ~3.4 km north of Skanderbeg Square). Right direction, approximate curve.",
			type = "primary",
			width = 14,
			points = { {0, -650}, {250, -1800}, {712, -3308} },
		},
		{
			name = "Rruga Babrru - Kamëz",
			description = "Northwest from Babrru to Kamëz (real position). Right direction, approximate curve.",
			type = "primary",
			width = 14,
			points = { {712, -3308}, {-1500, -4800}, {-4322, -6178} },
		},
		{
			name = "Babrru - Rruga 1 (E-W)",
			description = "Babrru neighborhood street - a stand-in grid around Babrru's real center, not its real street plan.",
			type = "local",
			width = 8,
			points = { {562, -3458}, {712, -3458}, {862, -3458} },
		},
		{
			name = "Babrru - Rruga 2 (E-W)",
			description = "Babrru neighborhood street - a stand-in grid around Babrru's real center, not its real street plan.",
			type = "local",
			width = 8,
			points = { {562, -3308}, {712, -3308}, {862, -3308} },
		},
		{
			name = "Babrru - Rruga 3 (E-W)",
			description = "Babrru neighborhood street - a stand-in grid around Babrru's real center, not its real street plan.",
			type = "local",
			width = 8,
			points = { {562, -3158}, {712, -3158}, {862, -3158} },
		},
		{
			name = "Babrru - Rruga 4 (N-S)",
			description = "Babrru neighborhood street - a stand-in grid around Babrru's real center, not its real street plan.",
			type = "local",
			width = 8,
			points = { {562, -3458}, {562, -3308}, {562, -3158} },
		},
		{
			name = "Babrru - Rruga 5 (N-S)",
			description = "Babrru neighborhood street - a stand-in grid around Babrru's real center, not its real street plan.",
			type = "local",
			width = 8,
			points = { {712, -3458}, {712, -3308}, {712, -3158} },
		},
		{
			name = "Babrru - Rruga 6 (N-S)",
			description = "Babrru neighborhood street - a stand-in grid around Babrru's real center, not its real street plan.",
			type = "local",
			width = 8,
			points = { {862, -3458}, {862, -3308}, {862, -3158} },
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
		-- Outer districts at their real positions (converted from their
		-- published latitude/longitude - see the module docstring).
		{ name = "Babrru", position = {712, -3308} },
		{ name = "Kamëz", position = {-4322, -6178} },
		{ name = "Laprakë", position = {-2028, -1329} },
		{ name = "Kashar", position = {-8436, -2319} },
		{ name = "Kombinat", position = {-4327, 1484} },
		{ name = "Sauk", position = {1195, 3061} },
	},
}

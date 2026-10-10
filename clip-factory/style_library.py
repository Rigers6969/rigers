"""The biggest Shorts channels per niche (YouTube Data API, most-viewed Shorts of the last 12 months, October 2026).

Each has its most-viewed recent Short: "Learn these styles" reads those Shorts (on your PC) and saves each style
as a preset. Only the editing style is copied - never their footage or audio.
"""

NICHES = {
    "history": {"label": "History", "for": "History", "channels": [
        {"name": "GeoGlobeTales", "handle": "@geoglobetales", "subs": 2040000, "short_views_1y": 121339518, "url": "https://www.youtube.com/shorts/mB1U5W8nwTg", "title": "Why Chile Is So Long & So Thin 🇨🇱 🌶️ History of the Longest & Narrowest Country 🤯", "views": 32496591},
        {"name": "History by Mae", "handle": "@historybymae", "subs": 1920000, "short_views_1y": 77868523, "url": "https://www.youtube.com/shorts/iHD-pJlrRJE", "title": "The discovery of an ancient face cream from Roman Britain #history #art", "views": 32836070},
        {"name": "Historically", "handle": "@heyhistorically", "subs": 1540000, "short_views_1y": 71978243, "url": "https://www.youtube.com/shorts/qNQEn9L9ph8", "title": "60s before NUKE... (Japan) #shorts #4k #history #extra", "views": 27522483},
        {"name": "Zack D. Films", "handle": "@zackdfilms", "subs": 29000000, "short_views_1y": 116547583, "url": "https://www.youtube.com/shorts/pIZUyyun3eg", "title": "The Assassination That Started World War I 😱", "views": 65080319},
        {"name": "MORGAR | Human History", "handle": "@morgarreacts", "subs": 80300, "short_views_1y": 164323941, "url": "https://www.youtube.com/shorts/jW3H1gXRRO4", "title": "She became INVISIBLE to the beast #history #facts", "views": 46420943},
    ]},
    "business": {"label": "Business & scam stories", "for": "Paper Trail", "channels": [
        {"name": "Matthew Cox | Inside True Crime", "handle": "@insidetruecrime", "subs": 1260000, "short_views_1y": 208799265, "url": "https://www.youtube.com/shorts/10NUTvRLfW8", "title": "Perfect Scams FAILS Because Of THIS", "views": 37549844},
        {"name": "PureBusiness", "handle": "@purebusinesshorts", "subs": 48800, "short_views_1y": 18388560, "url": "https://www.youtube.com/shorts/cbDcYT7nImw", "title": "How Gillette Was Founded 🪒 #shorts #business", "views": 7616779},
        {"name": "SoulshareTV", "handle": "@soulsharetv", "subs": 923000, "short_views_1y": 14953942, "url": "https://www.youtube.com/shorts/0OtJgEG0F9s", "title": "He became a billionaire 😲 by selling seaweed 🌊💰 #shorts #movieclips #film", "views": 14953942},
        {"name": "JustSaySteven", "handle": "@justsaysteven", "subs": 387000, "short_views_1y": 3563282, "url": "https://www.youtube.com/shorts/1mawItWyAyk", "title": "How Valve Almost Went Bankrupt", "views": 3563282},
        {"name": "Zack D. Films", "handle": "@zackdfilms", "subs": 29000000, "short_views_1y": 25593094, "url": "https://www.youtube.com/shorts/O3APJBBPvW4", "title": "The Run That Raised A Billion Dollars 😮", "views": 14275385},
    ]},
    "science": {"label": "Science facts", "for": "The Forgotten Lab", "channels": [
        {"name": "FactoHolic", "handle": "@factoholic", "subs": 22700000, "short_views_1y": 650660777, "url": "https://www.youtube.com/shorts/1CXbPbHvxW0", "title": "A Hole Through The Earth 😱", "views": 93644269},
        {"name": "Cleo Abram", "handle": "@cleoabram", "subs": 8850000, "short_views_1y": 154127254, "url": "https://www.youtube.com/shorts/aAW3CxVDT3w", "title": "What’s Hidden Under Antarctica?", "views": 29010178},
        {"name": "Facts' Mine", "handle": "@factsmine", "subs": 19300000, "short_views_1y": 82758941, "url": "https://www.youtube.com/shorts/lsfQxp-pkT8", "title": "Universal Jugaadu NASA", "views": 23781353},
        {"name": "GYRUS SULCUS", "handle": "@gyrussulcus1908", "subs": 2500000, "short_views_1y": 73134740, "url": "https://www.youtube.com/shorts/KmbjZYwx-Rs", "title": "Whale's Milk  #dharmendrasir #gyrussulcus #facts #science #civilservices #education", "views": 30084955},
        {"name": "Science and fun", "handle": "@scienceandfun", "subs": 9970000, "short_views_1y": 48533444, "url": "https://www.youtube.com/shorts/cX5EHhurF6Q", "title": "Pata tha ? I Science Experiment #ashusir #scienceandfun #experiment #funny #facts", "views": 20420084},
    ]},
    "podcast": {"label": "Podcast clips", "for": "Hot Mic Moments", "channels": [
        {"name": "Theo Rogan Shorts", "handle": "@theoroganshorts", "subs": 358000, "short_views_1y": 315250592, "url": "https://www.youtube.com/shorts/pqvtHamV0M4", "title": "Katt Williams Can't Handle Theo Von 🤣", "views": 33404256},
        {"name": "Theo Cuts", "handle": "@theocuts", "subs": 113000, "short_views_1y": 47534888, "url": "https://www.youtube.com/shorts/YwNeb1Oq2eI", "title": "Theo Von Was Nervous Around Ella Langley 😂", "views": 23347947},
        {"name": "mind Bytecast ", "handle": "@mindbytecast", "subs": 192000, "short_views_1y": 28323801, "url": "https://www.youtube.com/shorts/SgVKnz0R5-o", "title": "Joe Rogan reacts to the time machine tweet", "views": 13868314},
        {"name": "IMPAULSIVE", "handle": "@impaulsive", "subs": 4820000, "short_views_1y": 27233069, "url": "https://www.youtube.com/shorts/TptTlgm77Jw", "title": "SteveWillDoIt Tries LUNCHLY 👀🧀", "views": 9031904},
        {"name": "The Union Brief", "handle": "@theunionbrief", "subs": 87400, "short_views_1y": 19846670, "url": "https://www.youtube.com/shorts/2439EX6wA8g", "title": "Joe Rogan FREAKED OUT Watching AI Answering Scary Questions", "views": 12330795},
    ]},
    "streamer": {"label": "Streamer clips", "for": "Chat Lost It", "channels": [
        {"name": "WClipMedia", "handle": "@wclipmedia", "subs": 431000, "short_views_1y": 615080566, "url": "https://www.youtube.com/shorts/s1dWPWS_5kk", "title": "Rakai Always Wearing Double Durags 😂", "views": 65967498},
        {"name": "deagzzzshorts", "handle": "@deagzzzshorts", "subs": 6780000, "short_views_1y": 527315362, "url": "https://www.youtube.com/shorts/5Vh5SU2XL8c", "title": "iShowSpeed Finally Fought Back in 2026 💪🔥", "views": 323705032},
        {"name": "Nexxo Recaps", "handle": "@nexxorecaps", "subs": 775000, "short_views_1y": 306072919, "url": "https://www.youtube.com/shorts/6SIuOBPYEwo", "title": "No way he guess that way at the end 😭 #ishowspeed", "views": 108188024},
        {"name": "Succesful Celebrity", "handle": "@succesfulcelebrity", "subs": 3530000, "short_views_1y": 144707001, "url": "https://www.youtube.com/shorts/gFL8_Vgj04Y", "title": "Rakai Pretended To End His Stream With Yona! 😭❤️", "views": 56393942},
        {"name": "BKVC", "handle": "@bkvcshorts", "subs": 246000, "short_views_1y": 98951585, "url": "https://www.youtube.com/shorts/jUV5-_NFC0Q", "title": "Kai Cenat Leaks iShowSpeed's Number After He Leaked KSI's! 😱😂", "views": 86387994},
    ]},
}

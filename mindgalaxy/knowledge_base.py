"""
mindgalaxy.knowledge_base
==========================

A hand-curated, offline knowledge base that gives each star its "gas
cloud": when a thought is about food, milk, cars, watches, houses,
pregnancy, maths and so on, the star is surrounded by nebulae -- one per
*facet* of that topic (cuisines, kinds of milk, cars by speed / mileage /
seating, watches by price and movement, ...). Every facet holds items with
their origin, key attributes, nutrition, ingredients and recipe steps.

Everything here is plain data, so it's easy to extend: add a topic dict to
TOPICS (keywords decide when it lights up) and, optionally, a line to
RELATIONS so thoughts about it interconnect with other topics.

Figures (calories, prices, speeds, mileage) are typical approximate values
for orientation, not quotes or medical advice.
"""
from __future__ import annotations

from typing import Any


def item(name: str, origin: str | None = None, summary: str | None = None, *,
         attrs: dict | None = None, nutrition: dict | None = None,
         ingredients: list | None = None, steps: list | None = None,
         steps_label: str = "Recipe") -> dict[str, Any]:
    """Build one knowledge item, dropping empty fields to keep payloads small."""
    out: dict[str, Any] = {"name": name}
    if origin:
        out["origin"] = origin
    if summary:
        out["summary"] = summary
    if attrs:
        out["attrs"] = attrs
    if nutrition:
        out["nutrition"] = nutrition
    if ingredients:
        out["ingredients"] = ingredients
    if steps:
        out["steps"] = steps
        out["steps_label"] = steps_label
    return out


def facet(name: str, items: list, blurb: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"name": name, "items": items}
    if blurb:
        out["blurb"] = blurb
    return out


def N(kcal, protein=None, carbs=None, fat=None, basis="per serving", **extra) -> dict:
    """Nutrition helper: N(149, "8 g", "12 g", "8 g", "per 1 cup", Calcium="276 mg")."""
    out = {"Basis": basis, "Calories": f"~{kcal} kcal"}
    if protein:
        out["Protein"] = protein
    if carbs:
        out["Carbs"] = carbs
    if fat:
        out["Fat"] = fat
    out.update(extra)
    return out


TOPICS: dict[str, dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# FOOD & COOKING
# ---------------------------------------------------------------------------
TOPICS["food"] = {
    "label": "Food & Cooking",
    "keywords": ["cook", "cooking", "cooked", "cooks", "chef", "eat", "eating", "ate", "food", "foods",
                 "foodie", "hungry", "recipe", "recipes", "dinner", "lunch", "breakfast", "brunch",
                 "meal", "meals", "bake", "baking", "cuisine", "dish", "dishes", "snack", "kitchen",
                 "delicious", "tasty", "pizza", "pasta", "curry", "biryani", "taco", "tacos", "sushi",
                 "noodles", "restaurant"],
    "phrases": ["dining out", "eat out"],
    "priority": 1.0,
    "facets": [
        facet("Italian", [
            item("Margherita Pizza", "Naples, Italy (legend ties it to Queen Margherita, 1889)",
                 "Thin, blistered crust with tomato, mozzarella and basil — the colours of the Italian flag.",
                 ingredients=["500 g flour (00 or bread)", "325 ml warm water", "7 g yeast", "10 g salt",
                              "400 g San Marzano tomatoes", "250 g fresh mozzarella", "Fresh basil", "Olive oil"],
                 steps=["Mix flour, water, yeast and salt; knead 10 min; let rise 1–2 h.",
                        "Crush tomatoes by hand with a pinch of salt.",
                        "Preheat the oven as hot as it goes (250–290 °C / 480–550 °F) with a stone or steel inside.",
                        "Stretch dough into thin rounds; spread tomato, tear over mozzarella, drizzle oil.",
                        "Bake 6–10 min until blistered; finish with fresh basil."],
                 nutrition=N(250, "11 g", "30 g", "9 g", "per large slice")),
            item("Spaghetti Carbonara", "Rome, Lazio (mid-20th century)",
                 "Silky sauce made only from eggs, Pecorino and pork fat — no cream.",
                 ingredients=["200 g spaghetti", "100 g guanciale (or pancetta)", "2 eggs + 2 yolks",
                              "60 g Pecorino Romano", "Black pepper"],
                 steps=["Boil spaghetti in salted water.",
                        "Crisp diced guanciale in a dry pan; turn off the heat.",
                        "Whisk eggs, yolks, grated Pecorino and lots of pepper.",
                        "Toss drained pasta with guanciale, then the egg mix and a splash of pasta water off the heat until creamy."],
                 nutrition=N(600, "25 g", "70 g", "25 g")),
            item("Risotto alla Milanese", "Milan, Lombardy",
                 "Saffron-gold risotto finished with butter and Parmigiano.",
                 ingredients=["300 g Carnaroli or Arborio rice", "1 onion", "1 L hot stock", "Pinch of saffron",
                              "100 ml white wine", "Butter", "Parmigiano-Reggiano"],
                 steps=["Sweat chopped onion in butter.", "Toast rice 2 min; add wine and let it evaporate.",
                        "Add hot stock a ladle at a time, stirring, ~18 min; stir in saffron steeped in stock.",
                        "Off heat, beat in cold butter and grated cheese (mantecatura)."],
                 nutrition=N(450, "12 g", "65 g", "14 g")),
        ]),
        facet("Indian", [
            item("Butter Chicken (Murgh Makhani)", "Delhi, India (Moti Mahal restaurant, 1950s)",
                 "Tandoori chicken in a buttery, gently spiced tomato-cream sauce.",
                 ingredients=["600 g chicken thighs", "150 g yogurt", "Garam masala, chili, turmeric",
                              "Ginger-garlic paste", "400 g tomato puree", "50 g butter", "100 ml cream",
                              "Kasuri methi (dried fenugreek)"],
                 steps=["Marinate chicken in yogurt, ginger-garlic and spices for 1 h or more.",
                        "Grill or pan-sear until charred.",
                        "Simmer tomato puree with butter, chili and garam masala 15 min; blend smooth.",
                        "Add cream, crushed kasuri methi and chicken; simmer 10 min. Serve with naan or rice."],
                 nutrition=N(490, "32 g", "12 g", "35 g")),
            item("Masala Dosa", "Udupi, Karnataka — South India",
                 "Crisp fermented rice-and-lentil crêpe wrapped around spiced potato.",
                 ingredients=["3 cups rice", "1 cup urad dal", "1 tsp fenugreek seeds", "4 potatoes",
                              "Mustard seeds, curry leaves, turmeric", "1 onion"],
                 steps=["Soak rice, dal and fenugreek 6 h; grind to a smooth batter; ferment 8–12 h.",
                        "Make masala: temper mustard seeds and curry leaves, add onion, turmeric and mashed potato.",
                        "Spread a ladle of batter thin on a hot griddle; drizzle oil until golden.",
                        "Fill with masala, fold, and serve with coconut chutney and sambar."],
                 nutrition=N(380, "9 g", "60 g", "11 g")),
            item("Chana Masala", "Punjab (North India & Pakistan)",
                 "Tangy chickpea curry — high in fibre and plant protein.",
                 ingredients=["2 cups cooked chickpeas", "1 onion", "2 tomatoes", "Ginger, garlic, green chili",
                              "Chana masala spice, cumin", "Amchur (dry mango powder)"],
                 steps=["Fry cumin, then onion until golden; add ginger, garlic and chili.",
                        "Add tomatoes and spices; cook until oil separates.",
                        "Add chickpeas and water; simmer 15 min, mashing a few to thicken.",
                        "Finish with amchur and coriander."],
                 nutrition=N(300, "12 g", "45 g", "8 g", Fiber="~12 g")),
        ]),
        facet("Mexican", [
            item("Tacos al Pastor", "Mexico City & Puebla — adapted from shawarma by Lebanese immigrants",
                 "Chile-achiote pork with charred pineapple on corn tortillas.",
                 ingredients=["1 kg pork shoulder, thinly sliced", "Guajillo & ancho chiles", "Achiote paste",
                              "Pineapple", "Vinegar, garlic, oregano", "Corn tortillas", "Onion, cilantro, lime"],
                 steps=["Blend soaked chiles, achiote, vinegar, garlic and pineapple juice; marinate pork 4 h+.",
                        "Sear or roast until edges char; chop.", "Grill pineapple slices and dice.",
                        "Serve on warm tortillas with onion, cilantro, salsa and lime."],
                 nutrition=N(480, "28 g", "45 g", "20 g", "per 3 tacos")),
            item("Guacamole", "Aztec central Mexico (āhuacamōlli)",
                 "Mashed avocado with lime, onion, chile and cilantro.",
                 ingredients=["3 ripe avocados", "1 lime", "½ onion", "1 jalapeño", "Cilantro", "Salt"],
                 steps=["Mash avocados coarsely.", "Fold in finely chopped onion, chile and cilantro.",
                        "Season with lime juice and salt; serve right away."],
                 nutrition=N(180, "2 g", "10 g", "16 g", "per ½ cup")),
            item("Chilaquiles", "Central Mexico",
                 "Fried tortilla pieces simmered in salsa and topped with crema, cheese and egg.",
                 ingredients=["Corn tortillas", "Salsa roja or verde", "Crema", "Queso fresco", "Onion", "Eggs"],
                 steps=["Cut tortillas into wedges and fry or bake until crisp.",
                        "Simmer salsa, toss in chips for 1–2 min.",
                        "Top with crema, crumbled cheese, onion and a fried egg."],
                 nutrition=N(450, "17 g", "45 g", "22 g")),
        ]),
        facet("East Asian", [
            item("Tonkotsu Ramen", "Fukuoka, Japan (noodles came from China in the early 1900s)",
                 "Creamy pork-bone broth with noodles, chashu and a soft egg.",
                 ingredients=["Pork bones (or rich stock)", "Soy tare", "Ramen noodles", "Chashu pork",
                              "Soft-boiled egg", "Scallions, nori"],
                 steps=["Simmer pork bones hard for 8–12 h (or use a quick rich stock).",
                        "Put tare in a bowl and pour over hot broth.",
                        "Cook noodles ~2 min, drain and add.", "Top with chashu, halved egg, scallions and nori."],
                 nutrition=N(650, "30 g", "70 g", "25 g", Sodium="high (~2,000 mg+)")),
            item("Kung Pao Chicken", "Sichuan, China (named after Qing official Ding Baozhen)",
                 "Numbing-spicy stir-fry with dried chiles, Sichuan pepper and peanuts.",
                 ingredients=["Chicken thigh, diced", "Dried red chiles", "Sichuan peppercorns", "Roasted peanuts",
                              "Soy sauce, black vinegar, sugar", "Garlic, ginger, scallion"],
                 steps=["Marinate chicken in soy and cornstarch 15 min.",
                        "Fry chiles and peppercorns briefly in hot oil.",
                        "Stir-fry chicken until cooked; add garlic, ginger, scallion.",
                        "Add sauce (soy, vinegar, sugar, starch) and peanuts; toss until glossy."],
                 nutrition=N(430, "30 g", "15 g", "27 g")),
            item("Bibimbap", "Korea (Jeonju is famous for it)",
                 "Rice bowl of seasoned vegetables, beef, egg and gochujang — mix before eating.",
                 ingredients=["Cooked rice", "Spinach, bean sprouts, carrots, mushrooms", "Beef (optional)",
                              "Egg", "Gochujang", "Sesame oil"],
                 steps=["Blanch or sauté each vegetable separately; season with sesame oil and salt.",
                        "Cook marinated beef.", "Arrange over rice, top with a fried egg.",
                        "Add gochujang and mix everything together."],
                 nutrition=N(550, "24 g", "80 g", "15 g")),
        ]),
        facet("Middle Eastern & North African", [
            item("Hummus", "The Levant (Lebanon, Syria, Palestine, Israel)",
                 "Smooth chickpea and tahini dip.",
                 ingredients=["2 cups cooked chickpeas", "⅓ cup tahini", "1 lemon", "1 garlic clove",
                              "Ice water", "Olive oil, cumin"],
                 steps=["Blend tahini and lemon until fluffy.", "Add chickpeas, garlic, salt; blend.",
                        "Stream in ice water until very smooth.", "Serve with olive oil and paprika."],
                 nutrition=N(100, "4 g", "8 g", "6 g", "per ¼ cup")),
            item("Falafel", "Egypt (ta'ameya, made with fava beans); chickpea version in the Levant",
                 "Crisp herby fritters made from soaked — not canned — beans.",
                 ingredients=["1 cup dried chickpeas, soaked overnight", "1 onion", "Parsley & cilantro",
                              "Garlic, cumin, coriander", "Salt, baking soda"],
                 steps=["Pulse soaked (uncooked) chickpeas with onion, herbs, garlic and spices.",
                        "Rest 30 min; stir in baking soda.", "Form balls and fry at 175 °C for 3–4 min.",
                        "Serve in pita with tahini sauce and salad."],
                 nutrition=N(330, "13 g", "32 g", "18 g", "per 4 pieces")),
            item("Shakshuka", "Tunisia & the Maghreb",
                 "Eggs poached in a spiced tomato-pepper sauce.",
                 ingredients=["4 eggs", "1 can tomatoes", "1 red pepper", "1 onion", "Garlic, cumin, paprika"],
                 steps=["Soften onion and pepper; add garlic and spices.",
                        "Add tomatoes; simmer 10 min.", "Make wells, crack in eggs, cover until set.",
                        "Serve with bread."],
                 nutrition=N(300, "16 g", "20 g", "17 g")),
        ]),
    ],
}

# ---------------------------------------------------------------------------
# MILK
# ---------------------------------------------------------------------------
TOPICS["milk"] = {
    "label": "Milk & Dairy",
    "keywords": ["milk", "milks", "dairy", "lactose", "paneer", "yogurt", "yoghurt", "curd", "ghee",
                 "cheese", "butter", "buttermilk", "cream", "milkshake", "latte"],
    "phrases": ["plant milk", "oat milk", "almond milk", "soy milk"],
    "priority": 1.6,
    "facets": [
        facet("Types of animal milk", [
            item("Whole cow's milk (3.25%)", "Cattle domesticated ~10,500 years ago in the Near East",
                 nutrition=N(149, "8 g", "12 g", "8 g", "per 1 cup (244 ml)", Calcium="~276 mg")),
            item("Skim cow's milk", "Fat removed by centrifuge",
                 nutrition=N(83, "8 g", "12 g", "0.2 g", "per 1 cup", Calcium="~299 mg")),
            item("Goat milk", "Widely drunk in the Mediterranean, Middle East, Africa and South Asia",
                 "Smaller fat globules; some people find it easier to digest.",
                 nutrition=N(168, "9 g", "11 g", "10 g", "per 1 cup", Calcium="~327 mg")),
            item("Buffalo milk", "India & Pakistan (largest producers); Italy for mozzarella di bufala",
                 "Rich and creamy — prized for paneer, ghee and mozzarella.",
                 nutrition=N(237, "9 g", "13 g", "17 g", "per 1 cup", Calcium="~412 mg")),
            item("Lactose-free milk", "Regular milk with the lactase enzyme added",
                 "Same nutrition as regular milk; tastes slightly sweeter."),
        ]),
        facet("Plant milks", [
            item("Soy milk (unsweetened)", "China (doujiang, centuries old)",
                 "Closest plant milk to dairy in protein.",
                 nutrition=N(80, "7 g", "4 g", "4 g", "per 1 cup")),
            item("Oat milk", "Sweden (Oatly, from Lund University research, 1990s)",
                 "Creamy; foams well for coffee.", nutrition=N(120, "3 g", "16 g", "5 g", "per 1 cup")),
            item("Almond milk (unsweetened)", "Medieval Middle East & Europe",
                 "Very low calorie, low protein.", nutrition=N(35, "1 g", "1 g", "2.5 g", "per 1 cup")),
            item("Coconut milk beverage", "South & Southeast Asia",
                 nutrition=N(45, "0 g", "1 g", "4.5 g", "per 1 cup")),
        ]),
        facet("Made from milk", [
            item("Paneer", "India", "Fresh, non-melting cheese for palak paneer, paneer tikka, curries.",
                 ingredients=["1 L whole milk", "2 tbsp lemon juice or vinegar"],
                 steps=["Bring milk to a boil.", "Stir in lemon juice until curds separate from greenish whey.",
                        "Strain through cheesecloth and rinse.", "Press under a weight 1–2 h; cut into cubes."],
                 nutrition=N(290, "18 g", "4 g", "22 g", "per 100 g")),
            item("Yogurt / Dahi", "Mesopotamia & Central Asia (~5000 BCE)",
                 "Milk fermented by live cultures; good for gut health.",
                 ingredients=["1 L milk", "2 tbsp plain yogurt with live cultures"],
                 steps=["Heat milk to ~85 °C (185 °F); cool to ~43 °C (110 °F).",
                        "Stir in the yogurt starter.", "Keep warm 6–10 h until set.", "Refrigerate."],
                 nutrition=N(150, "8.5 g", "11 g", "8 g", "per 1 cup whole-milk", Calcium="~296 mg")),
            item("Butter", "Ancient — churned for at least 4,000 years",
                 ingredients=["500 ml heavy cream", "Pinch of salt (optional)"],
                 steps=["Whip cream past whipped stage until it splits into butter and buttermilk (~10 min).",
                        "Drain buttermilk (drink it or bake with it).",
                        "Knead butter in ice water until the water runs clear.", "Salt if you like; chill."],
                 nutrition=N(102, "0 g", "0 g", "11.5 g", "per 1 tbsp")),
            item("Ghee", "India", "Clarified butter with a nutty taste and high smoke point (~250 °C).",
                 ingredients=["250 g unsalted butter"],
                 steps=["Melt butter on low heat.", "Simmer 15–20 min until solids turn golden and sink.",
                        "Strain through cloth into a clean jar."],
                 nutrition=N(120, "0 g", "0 g", "14 g", "per 1 tbsp")),
            item("Mozzarella", "Campania, Italy",
                 ingredients=["4 L milk (not ultra-pasteurized)", "1½ tsp citric acid", "¼ tsp rennet", "Salt"],
                 steps=["Stir citric acid into milk; heat to 32 °C (90 °F).", "Add rennet; rest 5 min to set.",
                        "Cut the curd; heat to 40 °C (105 °F); drain.",
                        "Stretch curds in ~80 °C water until glossy; shape into balls."],
                 nutrition=N(85, "6 g", "1 g", "6 g", "per 1 oz (28 g)")),
        ]),
        facet("Dishes with milk", [
            item("Kheer (rice pudding)", "India (Sanskrit 'kshira' = milk)",
                 ingredients=["1 L whole milk", "¼ cup basmati rice", "½ cup sugar", "Cardamom, saffron",
                              "Almonds, pistachios"],
                 steps=["Bring milk to a boil; add washed rice.", "Simmer 30–40 min, stirring, until thick.",
                        "Add sugar, cardamom and saffron.", "Garnish with nuts; serve warm or chilled."],
                 nutrition=N(280, "8 g", "42 g", "9 g")),
            item("Masala Chai", "India",
                 ingredients=["1 cup water", "1 cup milk", "2 tsp black tea", "Ginger, cardamom, cinnamon, clove",
                              "Sugar to taste"],
                 steps=["Boil water with crushed ginger and spices 2 min.", "Add tea; brew 1–2 min.",
                        "Add milk and sugar; bring to a boil.", "Strain and serve."],
                 nutrition=N(120, "4 g", "16 g", "4 g", "per cup")),
            item("Tres Leches Cake", "Latin America (Mexico & Nicaragua)",
                 "Sponge cake soaked in three milks.",
                 ingredients=["Sponge cake", "Evaporated milk", "Sweetened condensed milk", "Heavy cream",
                              "Whipped cream, cinnamon"],
                 steps=["Bake a light sponge and poke holes all over.",
                        "Pour over the three milks mixed together.", "Chill overnight.",
                        "Top with whipped cream and cinnamon."],
                 nutrition=N(380, "8 g", "50 g", "16 g", "per slice")),
            item("Béchamel sauce", "France (17th century)",
                 "Base for lasagna, mac & cheese and croque monsieur.",
                 ingredients=["30 g butter", "30 g flour", "500 ml warm milk", "Salt, nutmeg"],
                 steps=["Melt butter; whisk in flour 1–2 min.", "Gradually whisk in warm milk.",
                        "Simmer until thick; season with salt and nutmeg."],
                 nutrition=N(90, "3 g", "7 g", "5 g", "per ¼ cup")),
        ]),
    ],
}

# ---------------------------------------------------------------------------
# CARS
# ---------------------------------------------------------------------------
def car(name, origin, zero60, top, mileage, seats, price, summary=None):
    return item(name, origin, summary, attrs={"0–60 mph": zero60, "Top speed": top, "Mileage / range": mileage,
                                              "Seats": seats, "Price (new, approx.)": price})


TOPICS["car"] = {
    "label": "Cars",
    "keywords": ["car", "cars", "vehicle", "vehicles", "suv", "suvs", "sedan", "hatchback", "truck", "pickup",
                 "minivan", "ev", "evs", "tesla", "automobile", "drive", "driving", "convertible", "hybrid"],
    "phrases": ["buy a car", "new car", "electric car", "road trip"],
    "priority": 1.3,
    "facets": [
        facet("By speed", [
            car("Chevrolet Corvette Stingray (C8)", "USA", "~2.9 s (Z51)", "~194 mph", "~19 mpg", "2", "~$70,000"),
            car("Tesla Model 3 Performance", "USA", "~2.9 s", "~163 mph", "~300 mi EV range", "5", "~$55,000"),
            car("Porsche 911 Carrera", "Germany", "~3.9 s", "~180 mph", "~20 mpg", "4 (2+2)", "~$120,000+"),
            car("Ford Mustang GT", "USA", "~4.2 s", "~155 mph (limited)", "~18 mpg", "4", "~$45,000"),
        ], "Fastest acceleration first"),
        facet("By mileage", [
            car("Toyota Prius", "Japan", "~7 s", "~112 mph", "up to ~57 mpg", "5", "~$29,000"),
            car("Toyota Corolla Hybrid", "Japan", "~9 s", "~110 mph", "~47–50 mpg", "5", "~$24,000"),
            car("Honda Civic", "Japan", "~7.5 s", "~125 mph", "~33–36 mpg", "5", "~$25,000"),
            car("Hyundai Ioniq 5", "South Korea", "~5–7 s", "~115 mph", "~245–318 mi EV range", "5", "~$43,000"),
        ], "Most efficient first"),
        facet("By seating", [
            car("Chevrolet Suburban", "USA", "~7 s", "~110 mph", "~17 mpg", "up to 9", "~$60,000"),
            car("Honda Odyssey", "Japan brand, built in Alabama", "~7 s", "~115 mph", "~22 mpg", "7–8", "~$40,000"),
            car("Kia Telluride", "South Korea brand, built in Georgia", "~7 s", "~120 mph", "~21 mpg", "7–8", "~$37,000"),
            car("Toyota Highlander Hybrid", "Japan", "~7.5 s", "~112 mph", "~35 mpg", "7–8", "~$45,000"),
        ], "Most seats first"),
        facet("By country of origin", [
            item("Japan", "Toyota, Honda, Mazda, Subaru, Nissan", "Known for reliability, resale value and hybrids."),
            item("Germany", "BMW, Mercedes-Benz, Audi, Porsche, Volkswagen", "Engineering, performance and luxury."),
            item("USA", "Ford, Chevrolet, Jeep, Tesla, Cadillac", "Trucks, muscle cars and EV pioneers."),
            item("South Korea", "Hyundai, Kia, Genesis", "Strong value and long warranties (often 10-yr powertrain in the US)."),
            item("Italy", "Ferrari, Lamborghini, Alfa Romeo, Fiat", "Design and supercars."),
            item("India", "Tata, Mahindra, Maruti Suzuki", "Affordable, rugged cars and SUVs."),
        ]),
    ],
}

# ---------------------------------------------------------------------------
# WATCHES & TIME
# ---------------------------------------------------------------------------
def watch(name, origin, movement, price, water, summary=None):
    return item(name, origin, summary, attrs={"Movement": movement, "Price (approx.)": price,
                                              "Water resistance": water})


TOPICS["watch"] = {
    "label": "Watches & Time",
    "keywords": ["watch", "watches", "wristwatch", "timepiece", "smartwatch", "clock", "clocks", "rolex",
                 "omega", "casio", "seiko", "chronograph", "punctual"],
    "phrases": ["lost track of time", "track of time", "what time", "on time", "running late", "always late", "be late", "keep time",
                "no time", "tell time", "apple watch"],
    "exclude": [r"\bwatch(ed|ing)? (a |the )?(movie|movies|film|tv|show|series|netflix|game|match|video)",
                r"\bwatch out\b", r"\bwatch(ed|ing)? over\b"],
    "priority": 1.2,
    "facets": [
        facet("Luxury (Swiss)", [
            watch("Rolex Submariner", "Switzerland", "Automatic", "~$9,000–$11,000 retail", "300 m",
                  "The classic dive watch since 1953."),
            watch("Omega Speedmaster Professional", "Switzerland", "Manual-wind chronograph", "~$7,000–$8,000",
                  "50 m", "The 'Moonwatch' worn on Apollo 11 (1969)."),
            watch("TAG Heuer Carrera", "Switzerland", "Automatic chronograph", "~$5,000–$7,000", "100 m"),
            watch("Patek Philippe Calatrava", "Switzerland", "Manual / automatic", "~$25,000+", "30 m",
                  "Minimal dress-watch icon."),
        ], "Resale prices are often higher than retail"),
        facet("Automatic (mid-range)", [
            watch("Orient Bambino", "Japan", "Automatic", "~$150–$250", "30 m"),
            watch("Seiko 5 Sports", "Japan", "Automatic", "~$250–$450", "100 m"),
            watch("Hamilton Khaki Field Mechanical", "Swiss-made, American heritage (Pennsylvania, 1892)",
                  "Hand-wound", "~$500–$600", "50 m"),
            watch("Tissot PRX Powermatic 80", "Switzerland", "Automatic (80-h reserve)", "~$700–$800", "100 m"),
        ]),
        facet("Quartz & digital", [
            watch("Casio F-91W", "Japan", "Digital quartz", "~$15–$25", "Splash resistant",
                  "One of the best-selling watches ever."),
            watch("Timex Weekender", "USA brand (Connecticut, 1854)", "Analog quartz", "~$40–$70", "30 m"),
            watch("Casio G-Shock DW-5600", "Japan", "Digital quartz", "~$50–$100", "200 m",
                  "Shock-resistant — practically indestructible."),
            watch("Citizen Eco-Drive", "Japan", "Solar-powered quartz", "~$150–$500", "100 m typical",
                  "Never needs a battery change for years."),
        ]),
        facet("Smartwatches", [
            watch("Garmin Forerunner", "USA (founded in Kansas, 1989)", "Smart (GPS sport)", "~$200–$600",
                  "50 m", "Battery lasts 1–2 weeks; built for runners."),
            watch("Apple Watch", "USA", "Smart (watchOS)", "~$249 (SE) – $799 (Ultra)", "50–100 m",
                  "Heart rate, ECG, fall detection; needs an iPhone."),
            watch("Samsung Galaxy Watch", "South Korea", "Smart (Wear OS)", "~$299+", "50 m"),
            watch("Google Pixel Watch", "USA", "Smart (Wear OS + Fitbit)", "~$349+", "50 m"),
        ]),
        facet("Movement types", [
            item("Automatic", None, "Wound by the motion of your wrist; no battery. Swiss/Japanese tradition."),
            item("Manual (hand-wound)", None, "You wind the crown every day or two; the oldest wristwatch tech."),
            item("Quartz", "Japan — Seiko Astron, 1969", "Battery + vibrating quartz crystal; accurate to seconds a month."),
            item("Solar", None, "Quartz charged by light."),
            item("Smart", None, "A tiny computer: notifications, health tracking, GPS; charge daily to weekly."),
        ]),
    ],
}

# ---------------------------------------------------------------------------
# PHONES
# ---------------------------------------------------------------------------
def phone(name, origin, os_, price, strength):
    return item(name, origin, strength, attrs={"OS": os_, "Price (approx.)": price})


TOPICS["phone"] = {
    "label": "Phones",
    "keywords": ["phone", "phones", "smartphone", "smartphones", "iphone", "android", "pixel",
                 "cellphone", "mobile", "oneplus", "xiaomi", "motorola"],
    "phrases": ["new phone", "cell phone"],
    "priority": 1.3,
    "facets": [
        facet("Flagships", [
            phone("Apple iPhone Pro", "USA (designed in California)", "iOS", "~$999–$1,199+",
                  "Long software support, strong video, Apple ecosystem."),
            phone("Samsung Galaxy S Ultra", "South Korea", "Android (One UI)", "~$1,299",
                  "Big zoom camera and built-in S Pen."),
            phone("Google Pixel Pro", "USA", "Android", "~$999", "Computational photography, AI features, 7 years of updates."),
            phone("OnePlus flagship", "China", "Android (OxygenOS)", "~$700–$900", "Very fast charging."),
        ]),
        facet("Budget (under ~$600)", [
            phone("Motorola Moto G", "USA brand (owned by Lenovo, China)", "Android", "~$150–$300", "Big batteries."),
            phone("Xiaomi Redmi Note", "China", "Android (HyperOS)", "~$200–$300", "Lots of specs for the money."),
            phone("Samsung Galaxy A series", "South Korea", "Android", "~$200–$450", "Long update support for the price."),
            phone("Google Pixel 'a' series", "USA", "Android", "~$499", "Flagship-class camera for less."),
            phone("Apple's lower-cost iPhone ('e' model)", "USA", "iOS", "~$599", "Cheapest way into current iOS."),
        ]),
        facet("Foldables", [
            phone("Motorola Razr", "USA brand", "Android", "~$699–$999", "Flip phone style."),
            phone("Samsung Galaxy Z Flip", "South Korea", "Android", "~$999+", "Folds to pocket size."),
            phone("Samsung Galaxy Z Fold", "South Korea", "Android", "~$1,799+", "Opens into a small tablet."),
            phone("Google Pixel Fold", "USA", "Android", "~$1,799", "Book-style foldable."),
        ]),
        facet("iOS vs Android", [
            item("iOS", "Apple, USA (2007)", "One maker, polished and consistent, long updates, iMessage/FaceTime."),
            item("Android", "Google, USA (2008)", "Many makers and prices, more customization, USB-C everywhere."),
        ]),
    ],
}

# ---------------------------------------------------------------------------
# TECHNOLOGY
# ---------------------------------------------------------------------------
TOPICS["technology"] = {
    "label": "Technology",
    "keywords": ["technology", "tech", "ai", "computer", "computers", "laptop", "software", "coding",
                 "programming", "internet", "robot", "robots", "gadget", "gadgets", "app", "apps",
                 "blockchain", "crypto", "python", "chatgpt", "claude", "algorithm", "algorithms"],
    "phrases": ["machine learning", "artificial intelligence"],
    "priority": 1.0,
    "facets": [
        facet("Major fields", [
            item("Artificial intelligence & ML", None, "Systems that learn from data — language models, vision, recommendations."),
            item("Cloud computing", None, "Renting computing power and storage over the internet (AWS, Azure, Google Cloud)."),
            item("Cybersecurity", None, "Protecting systems and data from attacks."),
            item("Blockchain", "Bitcoin whitepaper, 2008 (Satoshi Nakamoto)", "Shared, tamper-evident ledgers."),
            item("Internet of Things", None, "Everyday devices with sensors and connectivity."),
            item("Quantum computing", None, "Computers using qubits for certain problems classical machines find hard."),
        ]),
        facet("Landmark inventions", [
            item("ENIAC", "University of Pennsylvania, USA, 1945", "One of the first general-purpose electronic computers."),
            item("Transistor", "Bell Labs, New Jersey, USA, 1947", "The switch behind every chip."),
            item("ARPANET → Internet", "USA, 1969 (TCP/IP adopted 1983)"),
            item("World Wide Web", "CERN, Switzerland, 1989 — Tim Berners-Lee"),
            item("iPhone", "Apple, USA, 2007", "Made the touchscreen smartphone mainstream."),
            item("Transformer (AI)", "Google, 2017 — 'Attention Is All You Need'", "Architecture behind today's language models."),
        ]),
        facet("Learning paths", [
            item("Python", None, "Beginner-friendly; data analysis, automation, AI.",
                 steps=["Basics: variables, loops, functions.", "pandas for data.", "Build a small project.",
                        "Try scikit-learn for ML."], steps_label="Path"),
            item("Web development", None, "HTML, CSS, JavaScript, then a framework like React.",
                 steps=["HTML & CSS layout.", "JavaScript fundamentals.", "A framework (React/Vue).",
                        "Deploy on Vercel or Netlify."], steps_label="Path"),
            item("Data & analytics", None, "Excel/SQL → Python → dashboards (Power BI, Tableau)."),
        ]),
    ],
}

# ---------------------------------------------------------------------------
# HOUSE & HOME
# ---------------------------------------------------------------------------
TOPICS["house"] = {
    "label": "House & Home",
    "keywords": ["house", "houses", "home", "homes", "apartment", "flat", "rent", "renting", "mortgage",
                 "property", "condo", "villa", "realtor", "landlord", "neighborhood", "neighbourhood"],
    "phrases": ["real estate", "buy a house", "new house", "move out", "moving house"],
    "exclude": [r"\b(at|go|going|went|came|come|get|got|back|head|heading|drive|drove|walk|walked) home\b"],
    "priority": 1.1,
    "facets": [
        facet("Types of homes", [
            item("Single-family detached", None, "Own land and walls; most space and privacy, most upkeep."),
            item("Townhouse", None, "Shared walls, own entrance; often an HOA."),
            item("Condo / apartment", None, "A unit in a building; less maintenance, shared amenities."),
            item("Duplex", None, "Two units in one building — live in one, rent the other."),
            item("Tiny house", "USA movement, 2000s", "Under ~400 sq ft; low cost, minimal living."),
        ]),
        facet("Architectural styles", [
            item("Adobe / Pueblo Revival", "New Mexico & the US Southwest — Ancestral Puebloan roots",
                 "Sun-dried earth walls, flat roofs, vigas; naturally cool in summer."),
            item("Craftsman bungalow", "'Bungalow' comes from Bengali 'bangla'; popular in the US 1905–1930",
                 "Low-pitched roof, deep porch, handcrafted woodwork."),
            item("Victorian", "Britain & the US, 1837–1901", "Ornate trim, turrets, bold colours."),
            item("Colonial", "American colonies, 1600s–1700s", "Symmetrical, central door, two storeys."),
            item("Mediterranean / Spanish Revival", "1920s California & Florida", "Stucco walls, red tile roofs, arches."),
            item("Mid-century modern", "USA, ~1945–1970", "Open plans, big glass, flat planes."),
            item("Minka", "Japan", "Traditional timber-frame farmhouses."),
        ]),
        facet("Buying vs renting", [
            item("28/36 rule", None, "Housing ≤ 28% of gross income; all debt ≤ 36%."),
            item("Down payment", None, "Typically 3–20%; 20% on a conventional loan avoids PMI."),
            item("Mortgage types", None, "15-yr fixed (less interest), 30-yr fixed (lower payment), ARM (rate changes)."),
            item("Closing costs", None, "Roughly 2–5% of the price."),
            item("Buying checklist", None,
                 steps=["Check credit and budget.", "Get pre-approved.", "Tour homes with an agent.",
                        "Make an offer; get a home inspection.", "Appraisal, final walkthrough, close."],
                 steps_label="Steps"),
            item("Rent vs buy rule of thumb", None, "Buying usually pays off only if you'll stay ~5+ years."),
        ]),
    ],
}

# ---------------------------------------------------------------------------
# HOSPITAL
# ---------------------------------------------------------------------------
TOPICS["hospital"] = {
    "label": "Hospital & Care",
    "keywords": ["hospital", "hospitals", "doctor", "doctors", "nurse", "nurses", "clinic", "surgery",
                 "surgeon", "icu", "ambulance", "admitted", "checkup"],
    "phrases": ["emergency room", "urgent care", "see a doctor", "the er"],
    "priority": 1.2,
    "facets": [
        facet("Where to go", [
            item("Emergency room (ER)", None, "Life-threatening problems, 24/7. Call 911 (US) if in doubt."),
            item("Urgent care", None, "Same-day non-emergencies: sprains, minor cuts, fevers, UTIs."),
            item("Primary care", None, "Checkups, ongoing conditions, referrals."),
            item("Telehealth", None, "Video visits for minor issues, refills, mental health."),
            item("Specialist", None, "Cardiology, dermatology, etc. — usually by referral."),
        ]),
        facet("Hospital departments", [
            item("Cardiology", None, "Heart and blood vessels."),
            item("Obstetrics & Gynecology", None, "Pregnancy, birth and women's health."),
            item("Pediatrics", None, "Infants, children and teens."),
            item("Oncology", None, "Cancer care."),
            item("Orthopedics", None, "Bones, joints, sports injuries."),
            item("Neurology", None, "Brain and nerves — stroke, epilepsy, migraine."),
            item("Radiology", None, "X-ray, CT, MRI, ultrasound."),
            item("ICU", None, "Intensive care for critically ill patients."),
        ]),
        facet("Go to the ER for", [
            item("Stroke signs — BE FAST", None,
                 "Balance loss, Eyes (vision loss), Face drooping, Arm weakness, Speech trouble, Time to call 911."),
            item("Chest pain or pressure", None, "Especially with sweating, nausea or pain spreading to arm/jaw."),
            item("Trouble breathing", None),
            item("Severe bleeding, major injury, seizure, sudden severe pain", None),
        ]),
        facet("What to bring", [
            item("Checklist", None, steps=["Photo ID and insurance card.", "List of medications and doses.",
                                            "Allergies and medical history.", "Emergency contact.",
                                            "Phone charger.", "Advance directive, if you have one."],
                 steps_label="Bring"),
        ]),
    ],
}

# ---------------------------------------------------------------------------
# SCHOOL
# ---------------------------------------------------------------------------
TOPICS["school"] = {
    "label": "School",
    "keywords": ["school", "schools", "teacher", "teachers", "homework", "exam", "exams", "student",
                 "students", "kindergarten", "classroom", "lesson", "lessons", "study", "studying",
                 "preschool"],
    "phrases": ["high school", "middle school", "elementary school"],
    "priority": 1.1,
    "facets": [
        facet("Stages (US)", [
            item("Preschool / Pre-K", None, "Ages ~3–5: play, social skills, early letters and numbers."),
            item("Kindergarten", "Germany, 1837 — Friedrich Fröbel", "Age ~5–6."),
            item("Elementary", None, "Grades 1–5 (ages ~6–11): reading, writing, arithmetic."),
            item("Middle school", None, "Grades 6–8 (ages ~11–14)."),
            item("High school", None, "Grades 9–12 (ages ~14–18); diploma, AP/IB, SAT/ACT."),
        ]),
        facet("Types of schools", [
            item("Public", None, "Free, government-funded, local district."),
            item("Private", None, "Tuition-funded; often smaller classes."),
            item("Charter", "USA, 1990s", "Publicly funded, independently run."),
            item("Montessori", "Rome, Italy, 1907 — Maria Montessori", "Child-led, hands-on, mixed ages."),
            item("Waldorf", "Stuttgart, Germany, 1919 — Rudolf Steiner", "Arts, imagination, rhythm."),
            item("International Baccalaureate", "Geneva, Switzerland, 1968", "Global curriculum."),
            item("Homeschool", None, "Parent-led learning at home."),
        ]),
        facet("Study techniques", [
            item("Active recall", None, "Test yourself instead of re-reading."),
            item("Spaced repetition", "Based on Ebbinghaus's forgetting curve, Germany, 1885", "Review at growing intervals."),
            item("Pomodoro", "Italy, late 1980s — Francesco Cirillo", "25 min focus, 5 min break."),
            item("Feynman technique", "Named after physicist Richard Feynman", "Explain it simply to find gaps."),
            item("Interleaving", None, "Mix problem types instead of blocking one type."),
        ]),
    ],
}

# ---------------------------------------------------------------------------
# UNIVERSITY
# ---------------------------------------------------------------------------
TOPICS["university"] = {
    "label": "University",
    "keywords": ["university", "universities", "college", "colleges", "degree", "degrees", "campus",
                 "bachelor", "bachelors", "masters", "phd", "doctorate", "graduate", "graduation", "tuition",
                 "admission", "admissions", "major", "semester", "professor", "thesis", "scholarship"],
    "phrases": ["grad school", "master's degree"],
    "priority": 1.2,
    "facets": [
        facet("Degree levels", [
            item("Associate", None, "~2 years; community college."),
            item("Bachelor's", None, "~3–4 years (BA, BS, BTech)."),
            item("Master's", None, "~1–2 years (MS, MA, MBA)."),
            item("Doctorate", None, "~3–7 years (PhD, MD, EdD) with original research."),
        ]),
        facet("Oldest universities", [
            item("University of al-Qarawiyyin", "Fez, Morocco, 859 — founded by Fatima al-Fihri",
                 "Often cited as the oldest continuously operating degree-granting university."),
            item("Nalanda", "Bihar, India, 5th century CE", "Ancient Buddhist centre of learning; revived in 2014."),
            item("University of Bologna", "Italy, 1088", "Oldest in the Western world."),
            item("University of Oxford", "England, teaching by 1096"),
            item("Harvard University", "Massachusetts, USA, 1636", "Oldest in the US."),
        ]),
        facet("Study destinations", [
            item("USA", "MIT, Stanford, Harvard", "Flexible majors, research, high tuition, scholarships."),
            item("UK", "Oxford, Cambridge, Imperial", "Shorter degrees (3-yr bachelor's, 1-yr master's)."),
            item("Germany", "TU Munich, Heidelberg", "Little or no tuition at public universities."),
            item("Switzerland", "ETH Zurich, EPFL", "Top science & engineering."),
            item("Canada", "Toronto, UBC, McGill", "Post-study work options."),
            item("Singapore", "NUS, NTU", "Asia's top-ranked."),
            item("India", "IITs, IISc", "Highly competitive entrance exams (JEE)."),
        ]),
        facet("Applying", [
            item("Checklist", None, steps=["Shortlist programs.", "Tests (SAT/ACT, GRE/GMAT, TOEFL/IELTS).",
                                            "Statement of purpose / essays.", "Letters of recommendation.",
                                            "Financial aid: FAFSA (US) and scholarships.", "Submit before deadlines."],
                 steps_label="Steps"),
        ]),
    ],
}

# ---------------------------------------------------------------------------
# MATHS
# ---------------------------------------------------------------------------
TOPICS["maths"] = {
    "label": "Maths",
    "keywords": ["math", "maths", "mathematics", "algebra", "calculus", "geometry", "equation", "equations",
                 "formula", "formulas", "trigonometry", "statistics", "probability", "arithmetic", "solve",
                 "calculate", "fraction", "fractions", "percentage", "sqrt"],
    "phrases": ["square root", "math problem", "maths problem"],
    "priority": 1.2,
    "facets": [
        facet("Branches & origins", [
            item("Arithmetic", "Mesopotamia & Egypt, ~3000 BCE"),
            item("Geometry", "Euclid's Elements, Alexandria, ~300 BCE"),
            item("Zero as a number", "Brahmagupta, India, 628 CE"),
            item("Algebra", "al-Khwarizmi, Baghdad, ~820 CE ('al-jabr')"),
            item("Trigonometry", "Hipparchus (Greece, ~150 BCE); Aryabhata's sine tables (India, 499 CE)"),
            item("Probability", "Pascal & Fermat, France, 1654"),
            item("Calculus", "Newton (England) & Leibniz (Germany), 1660s–1680s"),
        ]),
        facet("Key formulas", [
            item("Quadratic formula", None, "x = (−b ± √(b² − 4ac)) / 2a"),
            item("Pythagorean theorem", None, "a² + b² = c²"),
            item("Circle", None, "Area = πr², circumference = 2πr"),
            item("Slope", None, "m = (y₂ − y₁) / (x₂ − x₁)"),
            item("Compound interest", None, "A = P(1 + r/n)^(nt)"),
            item("Percent change", None, "(new − old) / old × 100"),
        ]),
        facet("Try typing", [
            item("solve 2x + 3 = 11", None, "Linear equations are solved step by step."),
            item("solve x^2 - 5x + 6 = 0", None, "Quadratics show the discriminant and both roots."),
            item("what is 15% of 240", None, "Percentages."),
            item("sqrt(144) + 3^2", None, "Arithmetic with powers and roots."),
        ]),
    ],
}

# ---------------------------------------------------------------------------
# MARRIAGE
# ---------------------------------------------------------------------------
TOPICS["marriage"] = {
    "label": "Marriage & Weddings",
    "keywords": ["marriage", "married", "marry", "marrying", "wedding", "weddings", "engaged", "engagement",
                 "bride", "groom", "anniversary", "proposal", "propose", "honeymoon", "vows"],
    "phrases": ["get married", "getting married"],
    "priority": 1.3,
    "facets": [
        facet("Wedding traditions", [
            item("Hindu wedding", "India", "Saptapadi — seven steps around the sacred fire; mehndi, haldi, varmala."),
            item("Christian church wedding", "Europe & worldwide", "Vows, ring exchange, white dress."),
            item("Jewish wedding", None, "Chuppah canopy, ketubah contract, breaking of the glass."),
            item("Muslim Nikah", None, "Marriage contract with mahr (gift to the bride) and witnesses."),
            item("Chinese tea ceremony", "China", "Couple serves tea to elders; red for luck."),
            item("Shinto wedding", "Japan", "San-san-kudo: three sips from three sake cups."),
            item("Mexican wedding", "Mexico", "El lazo (unity lasso) and las arras (13 coins)."),
        ]),
        facet("Legal steps (US)", [
            item("Checklist", None, steps=["Apply for a marriage license at the county clerk (both partners, ID).",
                                            "Some states have a short waiting period; licenses expire (often 30–90 days).",
                                            "Ceremony with an officiant (and witnesses where required).",
                                            "Sign and return the license; order certified copies.",
                                            "If changing names: Social Security, then DMV, passport, banks."],
                 steps_label="Steps"),
        ]),
        facet("Anniversary gifts", [
            item("1st — Paper"), item("2nd — Cotton"), item("3rd — Leather"), item("5th — Wood"),
            item("10th — Tin / aluminum"), item("15th — Crystal"), item("25th — Silver"), item("30th — Pearl"),
            item("40th — Ruby"), item("50th — Gold"), item("60th — Diamond"),
        ]),
        facet("What keeps marriages strong", [
            item("5 : 1 ratio", "Gottman Institute research", "Stable couples have ~5 positive interactions per negative one during conflict."),
            item("Avoid the 'Four Horsemen'", "Gottman", "Criticism, contempt, defensiveness, stonewalling."),
            item("Antidotes", None, "Gentle start-up, appreciation, taking responsibility, taking a 20-min break to calm down."),
        ]),
    ],
}

# ---------------------------------------------------------------------------
# SPOUSE / PARTNER
# ---------------------------------------------------------------------------
TOPICS["spouse"] = {
    "label": "Spouse & Partner",
    "keywords": ["wife", "husband", "spouse", "partner", "girlfriend", "boyfriend", "fiance", "fiancee",
                 "fiancé", "fiancée", "romance", "romantic", "relationship"],
    "phrases": ["my love", "date night"],
    "priority": 1.3,
    "facets": [
        facet("Love languages", [
            item("Words of affirmation", "Gary Chapman, 'The 5 Love Languages', 1992", "Compliments, 'thank you', encouragement."),
            item("Quality time", None, "Undistracted attention — phones away."),
            item("Acts of service", None, "Doing the chores or errands they dread."),
            item("Receiving gifts", None, "Thoughtful tokens, not price tags."),
            item("Physical touch", None, "Hugs, holding hands, closeness."),
        ]),
        facet("Date & gift ideas", [
            item("Free", None, "Sunset walk, cook a new recipe together, handwritten letter, stargazing."),
            item("Under $50", None, "Picnic, museum day, flowers, a book they mentioned."),
            item("Special occasions", None, "Weekend getaway, concert, a class together (cooking, dance)."),
        ]),
        facet("Communication skills", [
            item("'I' statements", None, "'I feel … when … I need …' instead of 'You always …'."),
            item("Active listening", None, "Reflect back what you heard before responding."),
            item("Repair attempts", None, "Humor, a touch, 'Can we start over?' — de-escalates fights."),
            item("Weekly check-in", None, "What went well, what's hard, what do you need this week."),
        ]),
    ],
}

# ---------------------------------------------------------------------------
# SEXUAL HEALTH
# ---------------------------------------------------------------------------
TOPICS["sex"] = {
    "label": "Sexual Health & Intimacy",
    "keywords": ["sex", "sexual", "sexuality", "intimacy", "intimate", "contraception", "contraceptive",
                 "condom", "condoms", "libido", "sti", "stis", "std", "stds"],
    "phrases": ["birth control", "safe sex"],
    "priority": 1.3,
    "facets": [
        facet("Consent & communication", [
            item("FRIES", "Planned Parenthood", "Consent is Freely given, Reversible, Informed, Enthusiastic and Specific."),
            item("Talk openly", None, "Boundaries, desires, protection and testing — before, not after."),
        ]),
        facet("Contraception (typical-use effectiveness)", [
            item("Implant", None, attrs={"Effectiveness": ">99%", "Lasts": "up to 3–5 years"}),
            item("Hormonal / copper IUD", None, attrs={"Effectiveness": ">99%", "Lasts": "3–12 years"}),
            item("Injection", None, attrs={"Effectiveness": "~96%", "Lasts": "3 months"}),
            item("Pill, patch or ring", None, attrs={"Effectiveness": "~93%", "Lasts": "daily / weekly / monthly"}),
            item("External condom", None, "Also the main protection against STIs.",
                 attrs={"Effectiveness": "~87%", "Lasts": "single use"}),
            item("Withdrawal", None, attrs={"Effectiveness": "~80%"}),
        ], "Figures: CDC typical-use rates"),
        facet("STI prevention & testing", [
            item("Get tested", None, "CDC: everyone 13–64 tested for HIV at least once; sexually active women under 25 yearly for chlamydia & gonorrhea."),
            item("HPV vaccine", None, "Routinely at ages 9–12; recommended through 26."),
            item("PrEP", None, "Daily or injectable medicine that greatly lowers HIV risk when taken as prescribed."),
            item("Condoms", None, "Lower the risk of most STIs."),
        ]),
        facet("Wellbeing", [
            item("Stress, sleep & health", None, "Stress, poor sleep, some medicines and conditions affect desire — all common and treatable."),
            item("Talk to a clinician", None, "About pain, changes, or questions — it's routine for them."),
        ]),
    ],
    "note": "General education, not medical advice.",
}

# ---------------------------------------------------------------------------
# PREGNANCY
# ---------------------------------------------------------------------------
TOPICS["pregnancy"] = {
    "label": "Pregnancy",
    "keywords": ["pregnant", "pregnancy", "expecting", "trimester", "prenatal", "ultrasound", "conceive",
                 "conceiving", "fertility", "ivf", "obgyn"],
    "phrases": ["baby bump", "trying for a baby", "morning sickness", "due date"],
    "priority": 1.5,
    "facets": [
        facet("Trimesters", [
            item("First (weeks 1–13)", None, "Organs form; nausea and fatigue are common; first prenatal visit."),
            item("Second (weeks 14–27)", None, "Energy returns; movements felt ~16–25 weeks; anatomy scan ~18–22 weeks."),
            item("Third (weeks 28–40)", None, "Rapid growth; full term is 39–40 weeks."),
        ]),
        facet("Nutrition", [
            item("Folic acid", "CDC", "400 mcg daily, ideally starting before pregnancy — prevents neural tube defects."),
            item("Extra calories", "ACOG", "None in the 1st trimester, ~340/day in the 2nd, ~450/day in the 3rd."),
            item("Iron & calcium", None, "Iron ~27 mg/day; calcium ~1,000 mg/day (dairy, fortified foods)."),
            item("Avoid", None, "Alcohol; high-mercury fish (shark, swordfish, king mackerel); unpasteurized dairy; raw eggs; cold deli meats."),
        ]),
        facet("Checkups & tests", [
            item("Glucose screening", None, "Weeks 24–28 (gestational diabetes)."),
            item("Group B strep test", None, "Weeks 36–37."),
            item("Visit schedule", None, "Monthly to week 28, every 2 weeks to 36, then weekly."),
        ]),
        facet("Call your provider if", [
            item("Warning signs", None, "Bleeding, fluid leaking, severe headache or vision changes, severe belly pain, fever, sudden swelling of face/hands, or fewer baby movements."),
        ]),
    ],
    "note": "General information, not medical advice.",
}

# ---------------------------------------------------------------------------
# BIRTH
# ---------------------------------------------------------------------------
TOPICS["birth"] = {
    "label": "Birth & Newborns",
    "keywords": ["birth", "born", "labor", "labour", "delivery", "newborn", "newborns", "baby", "babies",
                 "childbirth", "midwife", "doula", "infant", "c-section", "cesarean"],
    "phrases": ["give birth", "gave birth", "going into labor"],
    "exclude": [r"\bbirthday\b"],
    "priority": 1.4,
    "facets": [
        facet("Types of delivery", [
            item("Vaginal birth", None, "Most common; typical hospital stay 1–2 days."),
            item("Cesarean (C-section)", None, "Surgical birth — about 1 in 3 US births; stay ~2–4 days."),
            item("VBAC", None, "Vaginal birth after a previous cesarean, when safe."),
            item("Water birth / birth center", None, "Low-intervention options for low-risk pregnancies."),
            item("Home birth", None, "With a qualified midwife, for low-risk pregnancies."),
        ]),
        facet("Stages of labor", [
            item("Stage 1", None, "Early labor, then active labor as the cervix opens to 10 cm."),
            item("Stage 2", None, "Pushing and the birth of the baby."),
            item("Stage 3", None, "Delivery of the placenta, usually within 30 minutes."),
        ]),
        facet("Newborn first days", [
            item("Apgar score", "Virginia Apgar, 1952", "Checked at 1 and 5 minutes (0–10)."),
            item("Skin-to-skin", None, "Warms baby, steadies breathing, helps feeding."),
            item("Feeding", None, "8–12 feeds in 24 hours; breast milk or formula."),
            item("Screening", None, "Heel-prick blood test and hearing test before discharge."),
            item("Umbilical stump", None, "Falls off in 1–3 weeks; keep it dry."),
        ]),
        facet("Traditions around the world", [
            item("Baby box", "Finland, since 1938", "Government gift of clothes and supplies; the box doubles as a bed."),
            item("Zuo yuezi ('sitting the month')", "China", "A month of rest and warming foods for the mother."),
            item("La cuarentena", "Latin America", "40 days of rest and care after birth."),
            item("Namkaran", "India", "Naming ceremony, often around day 12."),
            item("Satogaeri bunben", "Japan", "Returning to one's parents' home to give birth."),
        ]),
    ],
    "note": "General information, not medical advice.",
}

# ---------------------------------------------------------------------------
# CHILD & PARENTING
# ---------------------------------------------------------------------------
TOPICS["child"] = {
    "label": "Child & Parenting",
    "keywords": ["child", "children", "kid", "kids", "son", "daughter", "toddler", "toddlers", "parenting",
                 "parent", "parents", "teen", "teenager", "childhood", "nanny", "daycare"],
    "phrases": [],
    "priority": 1.2,
    "facets": [
        facet("Milestones (CDC)", [
            item("2 months", None, "Smiles when you talk to them."),
            item("6 months", None, "Rolls from tummy to back, laughs."),
            item("9 months", None, "Sits without support."),
            item("12 months", None, "Pulls to stand, waves bye-bye, says 'mama'/'dada'."),
            item("18 months", None, "Walks alone, says 3+ words."),
            item("2 years", None, "Kicks a ball, puts two words together."),
            item("3 years", None, "Short back-and-forth conversations."),
            item("5 years", None, "Counts to 10, tells simple stories."),
        ]),
        facet("Nutrition by age", [
            item("0–6 months", "WHO", "Breast milk or formula only."),
            item("~6 months", None, "Start solids — iron-rich foods first; no honey before age 1."),
            item("12 months", "AAP", "Whole cow's milk (about 16–24 oz/day); family foods."),
            item("2 years +", None, "Low-fat milk is fine; limit juice; no added sugar before 2."),
        ]),
        facet("Parenting styles", [
            item("Authoritative", "Diana Baumrind, 1966", "Warm with clear limits — linked to the best outcomes."),
            item("Authoritarian", None, "Strict rules, little warmth."),
            item("Permissive", None, "Warm, few limits."),
            item("Uninvolved", "Maccoby & Martin, 1983", "Low warmth, low limits."),
        ]),
        facet("Healthy habits", [
            item("Sleep", None, "Toddlers 11–14 h, school-age 9–12 h, teens 8–10 h (incl. naps)."),
            item("Screen time", "AAP", "Avoid under 18 months (except video chat); ~1 h/day of quality content ages 2–5."),
            item("Activity", "WHO", "Kids 5–17: 60 minutes of activity a day."),
            item("Vaccines & checkups", None, "Follow the well-child visit schedule."),
        ]),
    ],
}

# ---------------------------------------------------------------------------
# HEALTH & FITNESS
# ---------------------------------------------------------------------------
TOPICS["health"] = {
    "label": "Health & Fitness",
    "keywords": ["health", "healthy", "fitness", "exercise", "exercising", "workout", "workouts", "gym",
                 "diet", "sleep", "weight", "wellness", "running", "yoga", "stress", "meditation", "protein",
                 "calories", "nutrition", "vitamins", "walking", "cardio"],
    "phrases": ["lose weight", "work out", "mental health"],
    "priority": 1.0,
    "facets": [
        facet("Exercise", [
            item("Weekly target", "WHO / CDC", "150–300 min moderate (or 75–150 vigorous) activity + strength training 2 days."),
            item("Cardio", None, "Brisk walking, cycling, swimming, running."),
            item("Strength", None, "Weights, bodyweight, bands — all major muscle groups."),
            item("Yoga", "Ancient India", "Flexibility, balance and calm."),
        ]),
        facet("Sleep", [
            item("Adults", "CDC / AASM", "7 or more hours a night."),
            item("Better sleep", None, "Same schedule daily, dark cool room, screens off 1 h before bed, caffeine before noon."),
        ]),
        facet("Nutrition basics", [
            item("Half the plate", "USDA MyPlate", "Fruits and vegetables."),
            item("Fiber", None, "~25 g/day (women), ~38 g/day (men)."),
            item("Water", "NASEM", "~2.7 L/day (women), ~3.7 L/day (men) total from food and drink."),
            item("Protein", None, "~0.8 g per kg body weight minimum; more if very active."),
        ]),
        facet("Mental wellbeing", [
            item("Connection", None, "Regular time with people you trust."),
            item("Mindfulness", None, "Even 10 min/day of breathing or meditation lowers stress."),
            item("Get support", None, "Talk to a professional if low mood lasts 2+ weeks. US: call or text 988 in a crisis."),
        ]),
    ],
}

# ---------------------------------------------------------------------------
# DISEASE
# ---------------------------------------------------------------------------
def disease(name, cause, symptoms, prevention, summary=None, origin=None):
    return item(name, origin, summary, attrs={"Cause": cause, "Common symptoms": symptoms, "Prevention / care": prevention})


TOPICS["disease"] = {
    "label": "Disease & Illness",
    "keywords": ["disease", "diseases", "sick", "illness", "ill", "fever", "flu", "covid", "diabetes", "cancer",
                 "infection", "virus", "symptoms", "cough", "asthma", "allergy", "allergies", "hypertension",
                 "migraine", "headache", "strep", "diagnosis", "diagnosed"],
    "phrases": ["a cold", "caught a cold", "blood pressure", "heart disease", "sore throat"],
    "priority": 1.3,
    "facets": [
        facet("Common infections", [
            disease("Common cold", "Viruses — mostly rhinoviruses", "Runny nose, sore throat, sneezing; 7–10 days",
                    "Handwashing; rest and fluids"),
            disease("Influenza (flu)", "Influenza A & B viruses", "Sudden fever, aches, fatigue, cough",
                    "Yearly flu vaccine; antivirals work best within 48 h"),
            disease("COVID-19", "SARS-CoV-2 (first identified in Wuhan, China, 2019)",
                    "Fever, cough, fatigue, loss of taste/smell", "Vaccines, testing, staying home when sick"),
            disease("Strep throat", "Group A Streptococcus bacteria", "Sore throat, fever, usually no cough",
                    "Needs a test and antibiotics"),
        ]),
        facet("Chronic conditions", [
            disease("Type 2 diabetes", "Insulin resistance", "Thirst, frequent urination, fatigue — often none early",
                    "Activity, weight, diet; A1C ≥ 6.5% is diagnostic"),
            disease("Hypertension", "Many — genetics, salt, weight, stress", "Usually none ('silent')",
                    "≥ 130/80 mmHg is high (ACC/AHA); less sodium, exercise, medication"),
            disease("Asthma", "Airway inflammation", "Wheeze, cough, shortness of breath",
                    "Avoid triggers; controller and rescue inhalers"),
            disease("Heart disease", "Plaque in arteries", "Chest pain, breathlessness — can be silent",
                    "Leading cause of death worldwide; manage BP, cholesterol, smoking"),
        ]),
        facet("Prevention", [
            item("Vaccines", None, "Flu yearly; stay current on others by age."),
            item("Handwashing", None, "Soap and water for 20 seconds."),
            item("Screenings", None, "Blood pressure, cholesterol, blood sugar and age-based cancer screenings."),
            item("Lifestyle", None, "Sleep, activity, not smoking, moderate alcohol."),
        ]),
    ],
    "note": "General information, not medical advice.",
}

# ---------------------------------------------------------------------------
# INTERCONNECTIONS between topics: (a, b, why they're linked)
# ---------------------------------------------------------------------------
RELATIONS: list[tuple[str, str, str]] = [
    ("food", "milk", "Milk is a base for sauces, desserts, curries and chai"),
    ("food", "health", "What you eat shapes energy and long-term health"),
    ("food", "house", "The kitchen is the heart of a home"),
    ("food", "pregnancy", "Pregnancy changes nutritional needs and foods to avoid"),
    ("food", "child", "Kids' nutrition changes with age"),
    ("milk", "health", "Milk supplies calcium, protein and vitamin D"),
    ("milk", "child", "Breast milk or formula first, whole milk after age 1"),
    ("milk", "pregnancy", "Calcium needs rise; avoid unpasteurized dairy"),
    ("milk", "birth", "Newborns feed on breast milk or formula 8–12 times a day"),
    ("car", "technology", "EVs, driver-assist and software-defined cars"),
    ("car", "house", "Two of the biggest purchases most people make"),
    ("car", "child", "Family size drives seating and car-seat needs"),
    ("watch", "technology", "Smartwatches are wrist computers"),
    ("watch", "phone", "Smartwatches pair with your phone"),
    ("watch", "health", "Wearables track heart rate, sleep and activity"),
    ("phone", "technology", "Phones are the most-used computers on earth"),
    ("house", "marriage", "Couples often plan a home together"),
    ("house", "child", "Space, schools and safety shape family homes"),
    ("hospital", "health", "Checkups and care keep you healthy"),
    ("hospital", "disease", "Diagnosis and treatment"),
    ("hospital", "birth", "Most births happen in labor & delivery units"),
    ("hospital", "pregnancy", "Prenatal visits and delivery planning"),
    ("school", "child", "School stages follow a child's development"),
    ("school", "university", "School leads to higher education"),
    ("school", "maths", "Maths is a core subject at every grade"),
    ("university", "maths", "Maths underpins STEM degrees"),
    ("university", "technology", "Tech careers often start with a CS or engineering degree"),
    ("marriage", "spouse", "Married partners"),
    ("marriage", "sex", "Intimacy is part of a healthy partnership"),
    ("marriage", "pregnancy", "Family planning"),
    ("spouse", "sex", "Intimacy and communication go together"),
    ("sex", "pregnancy", "Contraception and family planning"),
    ("sex", "health", "Sexual health is part of overall health"),
    ("sex", "disease", "STI prevention and testing"),
    ("pregnancy", "birth", "Pregnancy leads to birth"),
    ("pregnancy", "health", "Prenatal health and nutrition"),
    ("birth", "child", "Birth begins childhood"),
    ("child", "health", "Vaccines, checkups and growth"),
    ("health", "disease", "Prevention vs treatment"),
    ("technology", "maths", "Algorithms, AI and cryptography are applied maths"),
]

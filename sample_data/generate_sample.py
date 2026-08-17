"""
Generates sample_data/journal_sample.json: a fictional but realistic six
month journal used to demo MindGalaxy. Spans several recurring life themes
(a novel-writing project that fades out, hiking, guitar, family, career
anxiety, workouts) plus a couple of one-off "shooting star" thoughts.

Run: python3 generate_sample.py
"""
import json
import datetime as dt
from pathlib import Path

NOW = dt.datetime(2026, 8, 17, 9, 0, 0)


def d(days_ago, hour=9):
    return (NOW - dt.timedelta(days=days_ago)).replace(hour=hour, minute=0, second=0).isoformat()


# (days_ago, text) — the novel-writing thread stops around day 95 (dormant),
# guitar starts fresh around day 60 (recent, active), everything else is
# spread fairly evenly to day 0.
ENTRIES = [
    # --- Novel project: intense at first, then goes quiet (dormant cluster) ---
    (180, "Started outlining the novel tonight. A lighthouse keeper who receives letters from a version of herself that never left the mainland. I don't know the ending yet and that's exciting."),
    (173, "Wrote the opening scene of the novel. The lighthouse keeper finds the first letter tucked into a delivery of oil for the lamp. Two thousand words, roughest draft imaginable, but it exists now."),
    (166, "Novel: figured out the antagonist isn't a person, it's the tide schedule itself. The letters only arrive during the lowest tides of the year. Structural constraint, love it."),
    (158, "Character work on the novel today. Her name is Mireille. She hasn't left the island in eleven years and everyone in the village has a theory about why."),
    (150, "Draft of chapter three of the novel. The other-self letters start contradicting each other and Mireille has to decide which life she trusts more."),
    (143, "Novel is stalling a bit — chapter four keeps wanting to be a flashback and I don't think it should be. Pushed through 800 words anyway."),
    (135, "Big novel breakthrough at 1am: the letters aren't from another timeline, they're from her future self, sent backward through the lighthouse lamp somehow. Rewriting chapter one tomorrow."),
    (126, "Rewrote the novel's opening with the new future-self concept. So much better. Sent the first three chapters to my writing group for feedback."),
    (118, "Writing group liked the novel pages a lot, said Mireille needs a stronger want in chapter two. Taking notes, feeling motivated."),
    (109, "Only wrote 300 words on the novel today, work was exhausting. Chapter five is proving hard because it's the first time Mireille lies to someone."),
    (101, "Haven't touched the novel in a week. Feeling guilty about it but also just tired. Maybe outline chapter six this weekend instead of drafting."),
    (95, "Opened the novel document, stared at it, closed it again. I think I need a break from Mireille for a bit, not abandoning it, just resting."),
    # (nothing on the novel after this — it goes dormant)

    # --- Career / job search anxiety ---
    (170, "Had a rough day at work. My manager keeps changing priorities mid-sprint and I'm starting to wonder if this team is sustainable long term."),
    (152, "Updated my resume for the first time in three years. It's humbling how much I've forgotten I even did."),
    (137, "Talked to a recruiter about a role at a smaller company. More ownership, less process, but also less stability. Don't know yet."),
    (120, "Second interview went fine I think? Hard to read the room over video calls. Trying not to obsess over it."),
    (104, "Didn't get the job. Disappointed but honestly relieved too — the pay bump wasn't enough to offset how chaotic that team sounded in the loop."),
    (88, "Work has been calmer this month. Maybe I don't need to leave, maybe I just needed a slower sprint."),
    (70, "Asked for a stretch project on the platform team. Scary to raise my hand but I want more technical depth, not just glue work."),
    (52, "Got the stretch project. Nervous-excited. First design doc due next week."),
    (34, "Presented my design doc today. Survived thirty minutes of questions from the staff engineers and only had to say 'let me get back to you' twice."),
    (16, "Design doc got approved with minor changes. First real system I get to own end to end. Trying to actually feel proud instead of immediately worrying about launch."),
    (4, "Launch prep for the platform project starting. Equal parts thrilled and terrified, which I think is just what caring about your work feels like."),

    # --- Trail running / hiking ---
    (176, "Ran the ridge trail for the first time this year. Legs are not ready but the view at the top never gets old."),
    (161, "Hiking with Dana on Saturday, she wants to attempt the full loop before it gets too hot. I said yes before thinking it through."),
    (147, "Did the full loop. Nine miles, way harder than I remembered, my knees are filing a complaint."),
    (131, "Short trail run before work today. Saw a family of deer right at the switchback. Good way to start a Monday."),
    (114, "Rain cancelled the weekend hike. Did a treadmill run instead which is objectively worse in every way but at least kept the streak alive."),
    (98, "New trail today, the one past the reservoir. Quieter than the ridge, way fewer people, might be my new favorite."),
    (81, "Running has been rough this month, motivation is low. Made myself do a short easy loop just to not lose the habit entirely."),
    (64, "Signed up for a half marathon in October. Terrifying commitment device but I think I need one."),
    (47, "First real training run for the half marathon. Pace felt slow but the plan says that's the point right now."),
    (29, "Long run day, 8 miles, and for the first time in weeks I actually enjoyed it instead of just gritting through it."),
    (12, "Trail run with Dana again, first time in months. She's training for the same half marathon, didn't even plan that, just happened."),

    # --- Family / parents ---
    (168, "Called Mom for her birthday, talked for an hour. She's finally getting the garden fence fixed after two summers of complaining about the deer."),
    (140, "Dad sent a long email about a project he's doing in the garage, restoring an old radio. He's happiest when he has something to take apart."),
    (112, "Sunday call with the family, my sister announced she's moving cities for a new job. Everyone's excited and a little sad at the same time."),
    (86, "Mom's garden fence is finally done. She sent seventeen photos of it from every angle, which is extremely her."),
    (60, "Helped Dad troubleshoot his radio project over video call, mostly by pointing at the screen and going 'is that wire supposed to be there.'"),
    (38, "Long overdue call with my sister in her new city. She sounds lighter than she has in years. Good decision, clearly."),
    (20, "Family group chat blew up over nothing, as usual, resolved itself within an hour, also as usual."),
    (6, "Planning a trip home for the holidays already, feels early but flights get expensive if I wait."),

    # --- Guitar (recent, fresh thread) ---
    (58, "Bought a used acoustic guitar on a whim. No idea if I'll stick with it but the store guy was very patient with my terrible strumming."),
    (51, "Learned my first three chords today. G, C, and D. My fingertips currently hate me."),
    (44, "Practiced for twenty minutes, fingers hurt less. Can almost switch between G and C without stopping the strum."),
    (37, "Learned a fourth chord, Em, and can now technically play about six songs badly. Very proud of this."),
    (30, "Tried to play along with a song for the first time. It was a disaster and also the most fun I've had all week."),
    (23, "Callus check: my fingertips are finally toughening up. Practice doesn't hurt anymore, just feels hard in a normal way."),
    (17, "Learned a barre chord. It sounded like a dying cat for the first ten tries and then suddenly, briefly, like an actual chord."),
    (10, "Played through a full song front to back without stopping for the first time. Recorded it as proof to future me who won't believe it."),
    (3, "Guitar practice at night has become my favorite part of the day, somehow. Didn't expect that when I bought it."),

    # --- Workouts ---
    (155, "Back at the gym after a long gap. Everything that used to be easy is not easy anymore, humbling."),
    (128, "Gym three times this week, which is a record for the year so far."),
    (96, "Skipped the gym for two weeks straight, work got in the way. Going back tomorrow, no more excuses."),
    (72, "Good lift today, hit a new number on the deadlift that I've been chasing for months."),
    (45, "Gym has started feeling like a habit instead of a chore, which took way longer than I expected."),
    (14, "Tried a new gym class with Dana before our run. Different muscles complaining today, in a good way."),

    # --- One-off "shooting star" thoughts: genuinely novel, unconnected ---
    (75, "Weird 2am thought: if a lighthouse sends light out in a rotating beam, is the darkness between beams also a kind of signal? Not sure why this felt profound at the time."),
    (41, "Idea I can't stop thinking about: a small business teaching people to fix their own bikes, run out of the garage on weekends. Probably nothing. Writing it down anyway."),
    (8, "Read something about octopuses possibly dreaming in color-changing patterns across their skin and now I can't think about anything else."),
]


def main():
    out = []
    for i, (days_ago, text) in enumerate(ENTRIES, start=1):
        out.append({"id": i, "text": text, "created_at": d(days_ago)})
    out.sort(key=lambda e: e["created_at"])
    for i, e in enumerate(out, start=1):
        e["id"] = i
    path = Path(__file__).parent / "journal_sample.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {len(out)} sample entries -> {path}")


if __name__ == "__main__":
    main()

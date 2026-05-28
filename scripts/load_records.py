"""Load user's actual vinyl collection into Russell's Records crate.
Wipes any existing 'Records' collection first, then bulk-inserts."""
import httpx
import sys

API = "http://localhost:8001/api"

# Data: (artist, album, genre)
RECORDS = [
    ("Albert, Herb & Brass Tijuana", "Going Places", ""),
    ("Allen, Woody", "The Night Club Years", ""),
    ("ARS", "A Rock and Roll Alternative", ""),
    ("Beatles", "Big band Beatles songs", ""),
    ("Beethoven, Ludwig Von", "Symphony No.7 in A minor", "Classical"),
    ("(Compilation)", "Best of 69", ""),
    ("Buck & Bubbles", "John W. that is", "Crooner"),
    ("Buffet, Jimmy", "Hot Water", "Rock"),
    ("Clegg Savuka, Johnny", "Cruel, Crazy, Beautiful World", "Reggae"),
    ("Cockburn, Bruce", "Humans", ""),
    ("Country Style", "Vol. 5", "Country"),
    ("Cummings, Burton", "My Own Way to Rock", ""),
    ("Cummings, Burton", "Cummings, Burton", ""),
    ("Domino, Fats", "Let the Four Winds Blow", ""),
    ("Dusty, Slim", "Encores", "Country"),
    ("Eastwood, Clint", "Paint Your Wagon", ""),
    ("Eminem", "Curtain Calls (Hits)", "Rap/HipHop"),
    ("Evans, Paul", "Hello This is…", ""),
    ("First Class", "The First Class", ""),
    ("Gibbs, Georgia", "Greatest Hits", ""),
    ("Focus", "Hamburger Concerto", "Classical"),
    ("Harmonic Choir", "Hearing Solar Winds", "Classical"),
    ("Harper, Don", "Australian Chamber Jazz", "Jazz"),
    ("Hunter", "Rempage Records EP", ""),
    ("Laine, Frankie", "Golden Hits", "Crooner"),
    ("Laine, Frankie", "Torchin'", "Crooner"),
    ("Lloyd Webber, Andrew", "Requiem", "Classical"),
    ("Lloyd Webber, Andrew", "Variations Aurora", ""),
    ("London Symphony", "All-Time Classics", "Classical"),
    ("M*A*S*H", "Original Soundtrack", ""),
    ("Marley, Bob", "Rastaman Vibrations", "Reggae"),
    ("Marstro's", "The Caribbean Sound", "Reggae"),
    ("Megatone Records", "Touch and Go", ""),
    ("Morgan, Russ", "Greatest Hits", ""),
    ("Morton, Jelly Roll", "And His Red Hot Peppers", "Jazz"),
    ("Nashville", "Best Of", "Country"),
    ("Pearson, Johnny", "Love Prelude", "Classical"),
    ("Pearson, Johnny", "Remember That Summer", ""),
    ("Pearson, Johnny", "Sleepy Shores", ""),
    ("Pearson, Johnny", "On Golden Pond", ""),
    ("Nilsson, Harry", "Portrait of Nilsson — 18 of His Greatest Hits", ""),
    ("Quantum Jump", "Quantum Jump", ""),
    ("Righteous Brothers", "Stars of Shindig", "60's"),
    ("Righteous Brothers", "Give it to the People", ""),
    ("(Compilation)", "Rock and Roll — Best Of", ""),
    ("Rodgers, Jimmie", "Both Sides Now", ""),
    ("Schubert", "Symphony No. 8", "Classical"),
    ("Sedaka, Neil", "Best Of", "Crooner"),
    ("Shearing, George", "Jazz Moments", "Jazz"),
    ("Temptations", "Greatest Hits", ""),
    ("Warner Bros", "Casino Lights", "Jazz"),
    ("Williams, Mason", "Ear Show", ""),
    ("Williams, Andy", "Moon River", ""),
]


def main():
    # 1. Wipe any existing 'Records' collection(s)
    existing = httpx.get(f"{API}/collections", timeout=20).json()
    wiped = 0
    for c in existing:
        if c.get("name", "").lower() == "records":
            httpx.delete(f"{API}/collections/{c['id']}", timeout=10)
            wiped += 1
    print(f"Wiped {wiped} existing Records collection(s)")

    # 2. Fresh Records collection
    r = httpx.post(
        f"{API}/collections",
        json={
            "name": "Records",
            "icon": "vinyl",
            "description": "My vinyl collection.",
        },
        timeout=10,
    ).json()
    rid = r["id"]
    print(f"Created Records collection: {rid}")

    # 3. Bulk add items
    added = 0
    for artist, album, genre in RECORDS:
        tags = [genre.strip()] if genre.strip() else []
        try:
            httpx.post(
                f"{API}/collections/{rid}/items",
                json={
                    "title": album.strip(),
                    "subtitle": artist.strip(),
                    "tags": tags,
                    "notes": "",
                    "rating": None,
                },
                timeout=10,
            )
            added += 1
        except Exception as e:
            print(f"  ✗ {artist} / {album}: {e}")
    print(f"Added {added}/{len(RECORDS)} records")


if __name__ == "__main__":
    main()

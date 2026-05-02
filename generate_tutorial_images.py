"""
Generate the tutorial reference images by running the same map-painting
pipeline the live game uses, with mock support data filled in. Produces:

  tutorialNationalMap.jpg      Painted national overview, ~mid-campaign
  tutorialStateZoom.jpg        Painted state district zoom for a sample state
  tutorialDashboard.png        Annotated diagram of the right-side dashboard
  tutorialSidebar.png          Annotated diagram of the left calendar sidebar

Run with:  python generate_tutorial_images.py
"""
import os
import random
import sys
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from State import State, District


# --- Constants pulled from CampaignGame.py to keep this generator standalone ---
PLAYER_COLORS = [(255, 0, 0), (0, 0, 255), (0, 255, 0), (128, 0, 128)]

CALENDAR_OF_CONTESTS = [
    ('Iowa', 4), ('New Hampshire', 5), ('Nevada', 7), ('South Carolina', 8),
    ('Minnesota', 9), ('Alabama', 9), ('Arkansas', 9), ('Colorado', 9),
    ('Georgia', 9), ('Massachusetts', 9), ('North Dakota', 9), ('Oklahoma', 9),
    ('Tennessee', 9), ('Texas', 9), ('Vermont', 9), ('Virginia', 9),
    ('Kansas', 10), ('Kentucky', 10), ('Louisiana', 10), ('Maine', 10),
    ('Nebraska', 10), ('Hawaii', 10), ('Michigan', 10), ('Mississippi', 10),
    ('Wyoming', 11), ('Florida', 11), ('Illinois', 11), ('Missouri', 11),
    ('North Carolina', 11), ('Ohio', 11), ('Arizona', 12), ('Idaho', 12),
    ('Utah', 12), ('Alaska', 13), ('Washington', 13), ('Wisconsin', 14),
    ('New Jersey', 15), ('New York', 15), ('Connecticut', 15), ('Delaware', 15),
    ('Maryland', 15), ('Pennsylvania', 15), ('Rhode Island', 15),
    ('Indiana', 16), ('West Virginia', 16), ('Oregon', 17), ('California', 19),
    ('Montana', 19), ('New Mexico', 19), ('South Dakota', 19),
]


def muted(color, saturation):
    return (int(color[0] * saturation + 255 * (1 - saturation)),
            int(color[1] * saturation + 255 * (1 - saturation)),
            int(color[2] * saturation + 255 * (1 - saturation)))


def load_states():
    """Build the states dict the same way setUpStates() does."""
    states = {}
    with open('statesPositions.txt', 'r') as f:
        for line in f:
            parts = line.split(',')
            if parts[0] != 'State Name':
                states[parts[0]] = State(parts[0], parts[1:])
    with open('districts.txt', 'r') as f:
        for line in f:
            parts = line.split(',')
            state_name = parts[0]
            d = District(parts[1].strip(), int(parts[2].strip()) * 3, state_name)
            states[state_name].addDistrict(d)
    return states


def populate_mock_support(states, num_players, current_date):
    """Stick some plausible support numbers on every district so the map has
    real polling to render. Player 1 (blue) and Player 2 (red) split the map
    along a real-world-ish red/blue axis."""
    blue_states = {
        'California', 'Connecticut', 'Delaware', 'Hawaii', 'Illinois', 'Maryland',
        'Massachusetts', 'New Jersey', 'New York', 'Oregon', 'Rhode Island',
        'Vermont', 'Washington', 'Colorado', 'Maine', 'Minnesota', 'Michigan',
        'New Hampshire', 'New Mexico', 'Nevada', 'Pennsylvania', 'Virginia',
        'Wisconsin',
    }
    rng = random.Random(42)
    for name, st in states.items():
        for i in range(num_players):
            st.setOrganization(i, 2 if i < 2 else 0)
        for d in st.districts:
            for i in range(num_players):
                d.setSupport(i, 0)
                d.setCampaigningThisTurn(i, 0)
                d.setAdsThisTurn(i, 0)
            if name in blue_states:
                blue, red = rng.uniform(45, 75), rng.uniform(15, 40)
            else:
                blue, red = rng.uniform(15, 40), rng.uniform(45, 75)
            blue += rng.uniform(-5, 5)
            red += rng.uniform(-5, 5)
            d.setSupport(0, int(round(blue)))
            d.setSupport(1, int(round(red)))
        st.updateSupport(num_players, CALENDAR_OF_CONTESTS, current_date)


def paint_national_map(image_path, states, current_date, past_elections):
    """Replica of CampaignGame.paintNationalMap, but standalone."""
    img = Image.open(image_path).convert('RGB')
    pixels = img.load()
    state_leaders = {}
    for s in states:
        for contest in CALENDAR_OF_CONTESTS:
            if contest[0] == s:
                if contest[1] < current_date:
                    if s in past_elections:
                        state_leaders[s] = [past_elections[s] - 1, 0.8]
                else:
                    support = states[s].pollingAverage
                    if support and max(support) > 0:
                        state_leaders[s] = [support.index(max(support)), 1.0]
                break
    with open('pixelList.txt', 'r') as f:
        for line in f:
            parts = line.split(',')
            x, y = int(parts[0]), int(parts[1])
            sname = parts[2].strip()
            if sname in state_leaders:
                leader, factor = state_leaders[sname]
                color = PLAYER_COLORS[leader]
                saturation = 0.70 if factor < 1.0 else 0.50
                pixels[(x, y)] = muted(color, saturation)
    return img


def paint_state_map(state_name, states):
    """Replica of paintStateMap with mock leader assignment per district."""
    path = os.path.join('stateDistricts', state_name + '.jpeg')
    img = Image.open(path).convert('RGB')
    pixels = img.load()
    district_leaders = {}
    for d in states[state_name].districts:
        if d.support and max(d.support) > 0:
            district_leaders[d.name] = d.support.index(max(d.support))
    px_path = os.path.join('stateDistricts', state_name + '.txt')
    with open(px_path, 'r') as f:
        for line in f:
            parts = line.split(',')
            if len(parts) < 4:
                continue
            x, y = int(parts[0]), int(parts[1])
            state_in_file = parts[2].strip()
            district = parts[3].strip()
            if state_in_file.lower() != state_name.lower():
                continue
            if district in district_leaders:
                pixels[(x, y)] = muted(PLAYER_COLORS[district_leaders[district]], 0.50)
    return img


def annotate(image, annotations, out_path):
    """Draw labeled arrows on top of an image. annotations is a list of
    (label, (x, y), side) where side is 'right' (default) or 'left'.
    Boxes that would run off the image edge are flipped to the other side."""
    img = image.copy()
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 18)
    except (IOError, OSError):
        font = ImageFont.load_default()
    img_w, img_h = img.size
    pad = 5
    for entry in annotations:
        if len(entry) == 2:
            label, (x, y) = entry
            side = 'right'
        else:
            label, (x, y), side = entry
        # Measure the text first so we can anchor without overflow.
        text_bbox = draw.textbbox((0, 0), label, font=font)
        tw = text_bbox[2] - text_bbox[0]
        th = text_bbox[3] - text_bbox[1]

        offset_y = -24
        if side == 'right':
            bx = x + 25
        else:
            bx = x - 25 - tw
        by = y + offset_y

        # Clamp to keep the label inside the image.
        if bx + tw + pad > img_w - 4:
            bx = img_w - 4 - pad - tw
        if bx - pad < 4:
            bx = 4 + pad
        if by - pad < 4:
            by = 4 + pad
        if by + th + pad > img_h - 4:
            by = img_h - 4 - pad - th

        draw.rectangle((bx - pad, by - pad, bx + tw + pad, by + th + pad),
                       fill=(255, 255, 224), outline=(0, 0, 0), width=2)
        draw.text((bx, by), label, fill=(0, 0, 0), font=font)
        # Arrow line from the box edge nearest the point to the point.
        anchor_x = bx + tw + pad if x > bx else bx - pad
        anchor_y = by + th // 2
        draw.line([(x, y), (anchor_x, anchor_y)], fill=(0, 0, 0), width=3)
        r = 6
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(0, 0, 0))
    img.save(out_path)


def make_dashboard_diagram():
    """A pure-PIL annotated mock of the right-side gameplay dashboard."""
    w, h = 420, 560
    img = Image.new('RGB', (w, h), (243, 239, 226))
    draw = ImageDraw.Draw(img)
    try:
        font_h = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 14)
        font_b = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 11)
    except (IOError, OSError):
        font_h = ImageFont.load_default()
        font_b = ImageFont.load_default()

    def card(y0, height, title, body_lines):
        draw.rectangle((12, y0, w - 12, y0 + height), fill='white', outline=(120, 120, 120))
        draw.text((20, y0 + 6), title, fill=(20, 54, 66), font=font_h)
        for i, line in enumerate(body_lines):
            draw.text((20, y0 + 28 + i * 16), line, fill=(0, 0, 0), font=font_b)

    card(12, 170, 'Campaign Dashboard', [
        'Time: 80    Money: $112,500',
        'Momentum: 18.4',
        '',
        "Headline:",
        "  Hospital closures hit rural communities",
        "Issue: Healthcare",
        "Your stance: Public Option",
        '',
        'Standings',
        'You: 142 delegates',
        'Bot: 98 delegates',
    ])
    card(196, 70, 'Fundraising time', [
        'Drag the slider below to send hours to fundraising.',
        '[ slider ]   24 / 80',
    ])
    card(280, 60, 'Actions', [
        '[ Review Report ]   [ End Turn ]',
    ])
    card(354, 110, 'This Week', [
        'Voting this week:',
        '  Wyoming, Florida, Illinois, Missouri,',
        '  North Carolina, Ohio',
        '',
        'Tip: Last-minute campaigning is +20% support.',
    ])

    return img


def make_sidebar_diagram():
    w, h = 360, 560
    img = Image.new('RGB', (w, h), (243, 239, 226))
    draw = ImageDraw.Draw(img)
    try:
        font_h = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 14)
        font_b = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 11)
    except (IOError, OSError):
        font_h = ImageFont.load_default()
        font_b = ImageFont.load_default()

    draw.rectangle((12, 12, w - 12, 80), fill='white', outline=(120, 120, 120))
    draw.text((20, 18), 'Calendar and Search', fill=(20, 54, 66), font=font_h)
    draw.text((20, 38), 'Search for a state', fill=(0, 0, 0), font=font_b)
    draw.rectangle((20, 54, 200, 70), fill=(255, 255, 255), outline=(80, 80, 80))
    draw.text((25, 56), 'Iowa', fill=(0, 0, 0), font=font_b)

    rows = [
        ('[Done]   * Iowa - wk 4 (12 del)',     (220, 220, 220), None),
        ('[Now]   * Massachusetts - wk 9 (30 del)', (214, 240, 194), 'Office $20k'),
        ('Tennessee - wk 9 (27 del)',           (255, 255, 255), 'Ballot $10k'),
        ('* Texas - wk 9 (108 del)',            (214, 240, 194), 'Office $10k'),
        ('Florida - wk 11 (81 del)',            (255, 255, 255), 'Ballot $10k'),
        ('* California - wk 19 (159 del)',      (214, 240, 194), 'Build $20k'),
        ('* New York - wk 15 (81 del)',         (214, 240, 194), 'Office $20k'),
    ]
    y = 96
    for label, bg, action in rows:
        draw.rectangle((12, y, w - 12, y + 28), fill=bg, outline=(140, 140, 140))
        draw.text((18, y + 7), label, fill=(0, 0, 0), font=font_b)
        if action:
            bw = 78
            draw.rectangle((w - bw - 16, y + 4, w - 16, y + 24), fill=(230, 230, 230), outline=(80, 80, 80))
            draw.text((w - bw - 12, y + 7), action, fill=(0, 0, 0), font=font_b)
        y += 32

    return img


def main():
    states = load_states()
    current_date = 8
    past_elections = {
        'Iowa': 1,
        'New Hampshire': 1,
        'Nevada': 2,
        'South Carolina': 2,
    }
    populate_mock_support(states, num_players=2, current_date=current_date)

    # Force a couple of Texas districts to flip so the "colored by leader"
    # tutorial label has actual visible variation.
    tx = states['Texas']
    for d in tx.districts:
        if d.name in ('Dallas-Fort Worth', 'Houston', 'East Texas'):
            d.support[0], d.support[1] = 60, 25  # player 0 (red) wins these
    tx.updateSupport(2, CALENDAR_OF_CONTESTS, current_date)

    # National map (replaces tutorialNationalMap.jpg).
    # Coordinates are tuned for nationalMap.jpg's actual geometry (~868x618).
    nat = paint_national_map('nationalMap.jpg', states, current_date, past_elections)
    iw, ih = nat.size
    annotations = [
        # Iowa is a past contest (darker shade) sitting roughly mid-map.
        ('Past contest (darker)',   (int(iw * 0.55), int(ih * 0.31)), 'left'),
        # Texas is mid-game leading (lighter shade).
        ('Leading - lighter shade', (int(iw * 0.42), int(ih * 0.66)), 'right'),
        # Florida is a swing state with upcoming contest - point at panhandle.
        ('Big upcoming contest',    (int(iw * 0.75), int(ih * 0.78)), 'left'),
    ]
    annotate(nat, annotations, 'tutorialNationalMap.jpg')

    # Sample state zoom (Texas).
    state_for_zoom = 'Texas'
    state_img = paint_state_map(state_for_zoom, states)
    sw, sh = state_img.size
    annotate(state_img,
             [('Each district colored by its leader', (int(sw * 0.30), int(sh * 0.62)), 'right'),
              ('Different leader, different color',   (int(sw * 0.78), int(sh * 0.45)), 'left'),
              ('Click a district to plan its spending', (int(sw * 0.55), int(sh * 0.85)), 'right')],
             'tutorialStateZoom.jpg')

    # Sidebar mockup.
    make_sidebar_diagram().save('tutorialSidebar.png')
    # Dashboard mockup.
    make_dashboard_diagram().save('tutorialDashboard.png')

    print('Wrote tutorialNationalMap.jpg, tutorialStateZoom.jpg, tutorialSidebar.png, tutorialDashboard.png')


if __name__ == '__main__':
    main()

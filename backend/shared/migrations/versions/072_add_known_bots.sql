-- Known Twitch bot accounts to exclude from Matcher viewer/overlap calculations.
CREATE TABLE IF NOT EXISTS known_bots (
    user_id  TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    note     TEXT
);

INSERT INTO known_bots (user_id, username, note) VALUES
    ('19264788',  'nightbot',              'Nightbot'),
    ('100135110', 'streamelements',        'StreamElements'),
    ('75338826',  'streamlabs',            'Streamlabs'),
    ('67080350',  'moobot',                'Moobot'),
    ('147152408', 'fossabot',              'Fossabot'),
    ('155260594', 'wizebot',               'Wizebot'),
    ('35902534',  'soundalerts',           'SoundAlerts'),
    ('237719812', 'tangiabot',             'TangiaBot'),
    ('702931064', 'commanderroot',         'CommanderRoot'),
    ('786974',    'sery_bot',              'Sery_Bot'),
    ('424596340', 'own3d',                 'OWN3D'),
    ('134458696', 'pretzelrocks',          'Pretzel Rocks'),
    ('95028921',  'kofi_bot',              'Ko-Fi Stream Bot'),
    ('1893919',   'twitchpresents',        'TwitchPresents'),
    ('18074328',  'twitchnotify',          'TwitchNotify'),
    ('552699291', 'streamelements',        'StreamElements Bot'),
    ('479191659', 'pokemoncommunitygame',  'Pokemon Community Game'),
    ('216527497', 'pidgeybot',             'PidgeyBot')
ON CONFLICT (user_id) DO NOTHING;

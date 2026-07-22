from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "instance_events" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "category" VARCHAR(32) NOT NULL,
    "detail" JSONB,
    "at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "actor_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE RESTRICT,
    "project_id" INT REFERENCES "projects" ("id") ON DELETE CASCADE,
    "subject_user_id" INT REFERENCES "users" ("id") ON DELETE RESTRICT
);
COMMENT ON COLUMN "instance_events"."category" IS 'ADMIN_GRANTED: admin_granted\nADMIN_REVOKED: admin_revoked\nMEMBERSHIP_ADDED: membership_added\nMEMBERSHIP_REMOVED: membership_removed\nFIRST_LOGIN: first_login\nOAUTH_LINKED: oauth_linked\nTOKEN_RESET: token_reset\nORG_CREATED: org_created\nPROJECT_CREATED: project_created\nUSER_CREATED: user_created\nUSER_DEACTIVATED: user_deactivated\nINVITE_CREATED: invite_created\nINVITE_REVOKED: invite_revoked';
        ALTER TABLE "users" ADD "first_login_at" TIMESTAMPTZ;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "users" DROP COLUMN "first_login_at";
        DROP TABLE IF EXISTS "instance_events";"""


MODELS_STATE = (
    "eJztXW1zm7gW/isMn3pn2k7ivmzH35yYtt42cYaQdmc3O4xsFFsbLLkgkvru7X+/IwHmTW"
    "BwsC1ifUuQDoYHvZzn0dHRv/qCOND1Xw+cBcKfPICp3tf+1TFYQL2vCUpfajpYLpMydoGC"
    "icurA1bPnrGKvABMfOqBKbvnHXB9+FLTHehPPbSkiGC9r+HAddlFMvWph/AsuRRg9COANi"
    "UzSOfQ0/vaX3+/1HSEHfgT+vG/y3v7DkHXyTw0cthv8+s2XS35tRGmH3lF9msTe0rcYIGT"
    "yssVnRO8ro3CF51BDD1AIbs99QL2+OzporeN3yh80qRK+IgpGwfegcClqdeticGUYIYfYm"
    "iyF5yxX3nVO33729sPb96//fBS0/mTrK/89it8veTdQ0OOwKWl/+LlgIKwBocxwc0jLiwi"
    "dz4HnoGDBYdvhH0K8BQWYIxtc0D61MsDGcNWhWR8IYEyaT4xlrofLKHHW5xewFS/vrkyzM"
    "HwYnTZ13IVN+O8AD9tF+IZnet97fR9BajfBub554H54vT9f9i9iQemYU+4jEp6vIjhnuDM"
    "+wd0bECLaA8BhRQtoLixZi1zWDuR6ev4j10h/8RW7EHgjLG7ijpIBbrW6MK4tgYXV+xNFr"
    "7/w+UQDSyDlfT41VXu6ov8l1jfRPs+sj5r7F/tz/GlwREkPp15/BeTetafOnsmEFBiY/Jo"
    "AyfVl+OrMTCZD+vBB3K/1YfNWrbwYaPH3eN37ch3jF+78kPG/WyyshtNJgW7zfOKJJ2yla"
    "klAZB4s2bIJQZbQbb/5t42YvEI0LTJFeyOFL/Ah14z5FIWx9RNmdt8dy90ABkiRQA/Eg+i"
    "Gf4CVwUXMIdbxBZuotvIh9+vuA3EV5Om74HHNZVINw2CbQe6kPIXNI1ryxydW3p+sGsBtb"
    "E3Axj9F/B3krHH1gUvGcoz2J0Prs8HQ0MvmWhVuxP5DzVaXzIB7A9CeRtfYTosQZCNghMw"
    "vX8EnmNnhkNWQnokd2Vdt1i06C3yVwAGMw4Dexn26BG88QcwHqBYaMlWqNRaUFTVhqyukl"
    "s6J7dMAYUz4gm6bT3JJW2/P9lFiKnOlRb7kzm4tIxhX0vpgNC5xWGpaXwbf0lKo556iy+M"
    "izPDvP48urIHwyGrsICLCfT8OVoy0parYxoX42+5Wh5ckAdW7+PIvLbsr+NPTPe5Q55PbZ"
    "fMEL7F48GN9dn+Orrkj0BAQOe2izB/Amv8xWDPd21YfY2Se8iezof0Fo/NT/a5aQz4W7GJ"
    "bepBwN/pyhz/bpxbSenSI//AKU1q3FwbZlLMXYps2dAYnFujb6lyB4IpRQ9hndHlt5FlJH"
    "dA+AFRmNwjKl/DGpVHuG4jdb3p1ZC63vRKpS5WlPXKHUgBcost/Pfr8aV4gEgs8ioImlLt"
    "f5qLfDkJTQV07G0z0kcM2YuLwR95NM+/js/ymga7wVkO2uYik1INpVQNwZSShtQ1bXJM3D"
    "UNWzzeNgIua3SkUokfTDgIzSUTgeURYVihnPAOqShsbmiqwV7TLUrxV2EPq4FiNKy1AOBV"
    "cqfOYpgd5MUi1KH4P3PRvyJ8Lyb/69INzJ87+oy9KNrfOdrP+aWY84uxWxu0Q/J3jl+GUr"
    "5/W4NSvn9bSilZUW6hrFtRKo8eouGclJNMTGMwNMy+xogN9G7xd3Nksf9Dg0g0icQSOeJW"
    "2O0DH/oN+n3a5Ig8xdzCpD0lARbMzlVLk4nN/gjeiTyowZ9L5EF/i1CarKUKpTlwKA1wXf"
    "IIHRsuAHJthywAwoIRpFwQLL2B0gcr9cGUDpyF+owQFwJcGU4iwHdCiLurgaep21of2rPx"
    "+GsG2rORlQP0hi0tvDjlOPs/XBQyheKQFAnvWwxJWUslwEomwMafp2noVcHuSD2cQymxHR"
    "WxK2TEQ+g4EmuJdYQccUdWUqJgeGqqhGU4jMBnO4usPn4xobuOWxOjGWpbN76ks1sZpr92"
    "rwYyTErFwAiwjVpg/IGUFCjbaF8lBQb+Vu5kykz5kpL5klF/bNYj0jbH5Amp+P123cewIb"
    "Xg+2RXouTDsa4LlOlZm/1Htf9hw/6HAy+fjgcBnY8ciCmiK5HTlK1Q6TiFEaAorIt24T39"
    "xfjLA3LCxuAHE/1v5VDt1qFKA153eTVtc+Aw6i3XWNsP22WNtQGEUfVuotd7964GfL1370"
    "rx42VKKz4K/165qWqb6bN3s9I7UUVeVm6naoWTlaqp9KnOuVO+Gwh2Nlf4AVF9FajGJ2vk"
    "L12wsvn/DVDM23XTrTrtfagTf9b7UB6AxsqUW/Vs3aqCh1BnJYrtwcxnmdt+VSqb164zK3"
    "2i1fcnItHJ9eKdrs7FiAgcoBRY5b5P+ru0LSxFGUf4fKtEpWftBe173lZ+UAf8oHtMHl3o"
    "zKDtAjwLwKwRsGLrreA9QPDajjc5KBfzGbmYh0xJ+Px0u4PkOZPI3Wya6KwOnxFkcXpKkF"
    "0ue5R0o3ctRpPf3/rUqMPuxTFk4OD7P9uhd1a8lbSjUHhwSjzHhg56alcx+Z0MB0k6lDeC"
    "o4WhI8Kj5sAhNyCtQHEBKegwEpQQ154C130iGBYh7jlwd7bzaw9QJHninogFW3C8WN+sY4"
    "jsQSoLZ5dyvWw9+2wUzexkzlMrhrIxhCqtLEyeOAf+vIkgkbVSq4eszAUTKEicWA7i2mCP"
    "yS10qVUyJeU8UymHJ0kVSJ6VO9sToz1ubF8POhLva1fbd9WmFRUNeHg5cWM04KEz/kmMnb"
    "wp/1JCk4AZZWWocl6UF742siL9DN4RD77yMVj6c0K1O+Jp8AF6K43dxA5vqDGF4LWe+xRN"
    "bRXP2v9RjWF7EMFXzhAyRt1cTd9BhnqeUKpRXMLaopsYts9VJ3y8sOPxoghmeXYvgemT8n"
    "odbo4SobmTxF5TF0FRNsHyFptY7FEbCDCLMxGczSpNs/Wh7yOChaPozc1oWBLelbHKARoE"
    "yHnNbGVefRUBGA6cIadPN0D+Lurgiecqo6iDJ1S6M5XurEMkttB/lXRSdeiEHOS/7LS/XN"
    "DFZvpf/6Q/fRzQV+Tu1QRgRwOBg6jmklmKyS8CCijCM43p4gRrBGtAC3+nKAg89WZKIVAK"
    "gVIIOoNh+1QrHBeaYJhYdBPDHexMULxf8X7F+xXvV7xf8X75oVO8X/H+4+b9fAtBKe2PNx"
    "hsZP2LuOJBIqFl4ZH7jedti0WW83PFKjvvyMu11tzAk1dMsqUGyM5qpBBvEWGetVQUSTaK"
    "FNB5Y46UtjkmT1+RJEWS5CNJvDcqlpQfmGSiSevNxQKSlN54XE6Rstuc1V5R2ca3KgZEo3"
    "1X9XeJkj3vb5Sb/Sgvvi0ggetut000bah8eOXDq+NclQuvXPiuuvDypEPrjAfPkRV47zHi"
    "5Z472+2qnPbOOe3sszVN5Ju26eJikEqJ3HJo3C6SvcAFQI3o5NqglcTH+22ROzmzTJ7cTd"
    "3n5ipDTZsZau6Q51PbJTO0zVJb0boFqi5VEKdMzDx+7UpqrjJzPSPNZatzfPjpPew7HuYs"
    "H4lYci6B7QO5Pxws8jDg7GyqGkk2P3omZ7wNpuwV9po5vjPQTEggmGOOMKl+PHGGyfX3mV"
    "dfUkCiUwYCvx0wbnxJvY1aYBCmMNrIgZgiip6KyHgQ0PkovNmqw6gUs1Fvj4k6gSEHiDqB"
    "QYhHxydgdQLDAU9gkHSmVQcw7PoAhhwwJQtyWeiql+bs3Edr+wTTOOtvvESuTjHddT4Q4p"
    "YsNRk4WBQW0rPbuSLbPUaNsf0RYQvJ5bUxjcHQMPsa09Cgd4u/myOL/R8a3OLB8GJ02de4"
    "ZKBvszilTpRUYme9ADMVKKUS56vE+YePjlKJ859j4vwB9NB0LvJlo5JKHxYkdVR8mWRjWp"
    "Wb+gA9v2GmsJRJN8NPdhLNw7pGk3RrYfVuAnh6clLHaT85KffaWVnObSeYCvfXlCezT5mo"
    "JPbFJPYNAgXan1h+/R8aTKPO"
)

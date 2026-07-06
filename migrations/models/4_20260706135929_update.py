from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "record_edits" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "record_id" VARCHAR(32) NOT NULL,
    "domain" VARCHAR(64) NOT NULL,
    "before_snapshot" JSONB NOT NULL,
    "client" VARCHAR(64) NOT NULL DEFAULT 'unknown',
    "session_id" UUID,
    "at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "actor_id" INT NOT NULL REFERENCES "users" ("id") ON DELETE CASCADE,
    "project_id" INT NOT NULL REFERENCES "projects" ("id") ON DELETE CASCADE
);
COMMENT ON TABLE "record_edits" IS 'Before-snapshot for every edit_record call.';"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "record_edits";"""


MODELS_STATE = (
    "eJztXVtT2zgU/iseP7EzwEAKlMlbAuk024Z0Qtju9DIexVYcLbKUyjI02+W/70i2Y1uxQ1"
    "ycYIPeYklHtj5dzvmOpJNfpkcdiP3DIXMBQf8Cjigx28YvkwAPmm0jN3/fMMF8nuSKBA4m"
    "WArQVEmZAyY+Z8DmZtuYAuzDfcN0oG8zNI9eRgKMRSK1fc4QcZOkgKAfAbQ4dSGfQWa2ja"
    "/f9w0TEQf+hH78OL+1pghiJ/PdyBHvlukWX8xlWp/wd7KgeNvEsikOPJIUni/4jJJlaUS4"
    "SHUhgQxwKKrnLBCfL74uam7covBLkyLhJ6ZkHDgFAeap5m6IgU2JwA8R7ssGuuItB63jk7"
    "cn52/OTs73DVN+yTLl7UPYvKTtoaBE4GpsPsh8wEFYQsKY4ObjwF1F7mIGWD50cXkFPJ8z"
    "FbwYqmdFzwM/LQyJy2dm2zg7WQPVX53RxfvOaO/s5A/REsqAHQ7wqyinJbMEmgl6DvLnGC"
    "ws+VwCRVWuGjTjhATOZAJuA8/j1vkGgB63zgsRlXlZSG0GRZMtwFcBvQQccuTBfFCzkgqk"
    "TiR6GP+oKcAMAmdI8CKaC2vwHfcHvetxZ/BJtMTz/R9YQtQZ90ROS6YulNS9M6UrlpUYn/"
    "vj94Z4NL4Mr3oSQepzl8k3JuXGX0zxTSDg1CL03gJOatrGqTEwD2K5nt6mFh6RMAH27T1g"
    "jpXJSUbAnNF/oM391f7vRpLvPowgXuompacjDfYprKWe3fwQj904Ne5ugQ9t0SLEVrO8lq"
    "emAAJc+dXi3eJNCiI56j4FVrGmT/dLtUr+q7AiRLVSu3zXOv8l6/xdaymt9Rug9W8JvcfQ"
    "caGFAXED4JYCNl/6t+CNpvLzoXu2CbiqGk9he6YNqhdsUKU7ljLXKqUCE4HH1WBNeq8CTb"
    "hig2YQXIXvHWUQueQDXEgU+8TngNh5K0qBr6R+MBaZm/uGycD90rJKDRBKLAdiyMOFt3N9"
    "0bnsmQ+bWO+c3kJSje0+FlU1C9HMBGXQpsyxoIOeSmZGsqaeg2o6T0vBcQdJRXiImhoPSC"
    "VQDCAHDUaCU4otG2D8RDDGlOILgHGDofCgN4HMn6H5E7G48SEbLCtrGCI78IOE2qXYGbLU"
    "Po96RKxE5+nNj7qZf+scIbLfrBnwZ2XYZlZKb4SIPAwmEJcBcSmwOyeIadbaBaJ5+gvl6c"
    "Dm6C7Hn9WlFENA8vs0EVL6c0Lp1syb5aLzFGWe12Xd4fBjpre6/bEyNW4G3d5o71h2k/8D"
    "o5B6xmv4yu5QOc9HVug1eT/S0AU+ZOVwS0m8JtDWuIwEIhX4jG6iauqH36a+otTQyHcW5U"
    "zaCoBr5Lauil12OSrra9smN0o5mnKYUdYNVcyLVMfXo6zI7MIpZfDAJ2Duzyg3ppQZ8A6y"
    "hSEqscIKDeEhODSVrigrq3nWznlWNB7y4CtmCBmhZm6VvmltQBPetApZgshStp6pBxApte"
    "m8lGgmhtVz1YlcL6x4vVgF88/r4VU+mDmiKt1CNjf+MzDy662j8tAU7c5Y6TGKe4PO3yrA"
    "Fx+HXZUsiQq6Kq3FKPLSbzpiE4kd+gYCIg4RkMpcBNUPWx/6PqIkdxW9uelfFpzdyUgpgA"
    "YBcg6FbC0PRqwBMFw4Q06fHoCyLVnYyrtTtBulrm4UWpK+pkVeE3/V/pJtUH9NYkuT2JX5"
    "q10nyrJUQ/IvT1UUs//40MXj9H950ONx/j8M+AGdHkwAcQwQOIgbmLopJu8FHHBEXEP4xS"
    "kxKDGAEb5n1SHw1Mq0h0B7CLSHoDEYVk+1wnWhDIaJRDMx3MKxc837Ne/XvF/zfs37Ne+v"
    "P3Sa92ve/7p5v7xCUEj74wsGj7J+Ly74LCeh68Ijd3uetyoWWczPNatsvCFfr73mEpa8Zp"
    "IVDcB7hjiH5DdOmGclNUWqG0UK+Kw0R0rLvCZLX5MkTZLqR5LkbNQsSV2Y6kSTlpeLc0hS"
    "+uJxMUXKXnPWd0Xrtr6tY0A8une1+S1RuuP7jfVmP9qKrwpIgPHvXRNNC2obXtvwzxPuTJ"
    "vw2oRvgh1adxP+2Tbmm2vBS2RzrPcY8WLLXdx21UZ744x20W1lo7SmZZq4GaTj3VZ8NG4b"
    "wV7qE3mo+cxSx1epMr6KDkP0ggjmU/5/wdKRXHUkVx3JVUdyrXsk1/oQYR3IdaeBXBVgCo"
    "h9Frr1FN9SOq3qv7mJo4fFrjb9VzfbvldIcQFl7ZHAW3HIZY+FRrI73H0S56zCEaLcjx31"
    "Ope9UdsQ5ilk38jnUX8snkOBb6RzOehftQ3geOGZyxrc/9I84uXwCL3hogNw1mSXSgfg1A"
    "E4d7K39zxbVB3IkD3Ls2WjnLU2LEjK6H2qmq1p68zUO8j8khEHUiLN3AhonZ5uYHO2Tk8L"
    "jU6Zp+wFzOdlQIyKNxPA46OjTYz2o6Niq13kKWY7JTz3nF5xUMyUiA6GuRoMs4QPvnrF8v"
    "A/SYxeGQ=="
)

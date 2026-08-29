import psycopg2


class Database:

    def __init__(self, url):
        self.conn = psycopg2.connect(url)

    def create_tables(self):
        try:
            with self.conn.cursor() as cursor:

                # Users
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        name TEXT,
                        age SMALLINT,
                        city TEXT,
                        gender TEXT,
                        profile_picture TEXT,
                        bio TEXT,
                        wallet_balance NUMERIC(12, 0) DEFAULT 5
                    )
                """)

                # Sponsor channels
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sponsor_channels (
                        channel_id BIGINT PRIMARY KEY,
                        invite_link TEXT NOT NULL
                    )
                """)

            self.conn.commit()

        except Exception:
            self.conn.rollback()
            raise

    # =========================
    # Users
    # =========================

    def add_user(self, user_id):
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO users (user_id)
                    VALUES (%s)
                    ON CONFLICT (user_id) DO NOTHING
                """, (user_id,))

            self.conn.commit()

        except Exception:
            self.conn.rollback()
            raise

    # =========================
    # Sponsor channels
    # =========================

    def get_sponsor_channels(self):

        try:

            with self.conn.cursor() as cursor:

                cursor.execute("""
                    SELECT channel_id, invite_link
                    FROM sponsor_channels
                    ORDER BY channel_id
                """)

                rows = cursor.fetchall()

                return [
                    {
                        "channel_id": row[0],
                        "invite_link": row[1]
                    }
                    for row in rows
                ]

        except Exception:

            self.conn.rollback()

            raise


    def add_sponsor_channel(self, channel_id, invite_link):

        try:

            with self.conn.cursor() as cursor:

                cursor.execute("""
                    INSERT INTO sponsor_channels
                    (channel_id, invite_link)
                    VALUES (%s, %s)
                    ON CONFLICT (channel_id) DO NOTHING
                    RETURNING channel_id
                """, (
                    channel_id,
                    invite_link
                ))

                result = cursor.fetchone()

            self.conn.commit()

            return result is not None

        except Exception:

            self.conn.rollback()

            raise


    def remove_sponsor_channel(self, channel_id):

        try:

            with self.conn.cursor() as cursor:

                cursor.execute("""
                    DELETE FROM sponsor_channels
                    WHERE channel_id = %s
                    RETURNING channel_id
                """, (
                    channel_id,
                ))

                result = cursor.fetchone()

            self.conn.commit()

            return result is not None

        except Exception:

            self.conn.rollback()

            raise

    # =========================
    # Close
    # =========================

    def close(self):
        if self.conn and not self.conn.closed:
            self.conn.close()
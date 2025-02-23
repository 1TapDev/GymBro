GymBro 🤖💪

A Discord bot that tracks gym check-ins, personal records, and user progress with a PostgreSQL database.

🚀 Features

✅ Gym Check-Ins – Users can log their gym visits, weight progress, and food intake.✅ Personal Records (PRs) – Track best lifts for deadlift, bench, and squat.✅ Progress Tracking – View total check-ins, weight changes, and logs.✅ Leaderboard – Shows top users based on points earned.

🛠️ Setup & Installation

1️⃣ Clone the Repository

git clone https://github.com/1TapDev/GymBro.git
cd GymBro

2️⃣ Install Dependencies

Make sure you have Python 3.10+ installed.

pip install -r requirements.txt

3️⃣ Set Up Environment Variables

Create a .env file in the root directory:

cp .env.example .env

Then update .env with your bot token and database details:

DATABASE_URL=postgresql://botuser:yourpassword@localhost:5432/gymbro
TOKEN=your_discord_bot_token

4️⃣ Set Up PostgreSQL Database

Ensure PostgreSQL is installed and running.Run the following commands to create the database:

psql -U postgres

CREATE DATABASE gymbro;
CREATE USER botuser WITH ENCRYPTED PASSWORD 'yourpassword';
GRANT ALL PRIVILEGES ON DATABASE gymbro TO botuser;

Now, apply the database schema:

psql -U botuser -d gymbro -f database/schema.sql

💪 Database is now ready!

5️⃣ Start the Bot

python main.py

🤖 Bot Commands

🏋️‍♂️ Check-Ins

Command

Description

/checkin gym

Log a gym check-in (requires a workout photo).

/checkin weight

Log weight progress (requires scale photo).

/checkin food

Log food intake (requires meal photo).

📊 Progress & PRs

Command

Description

/progress

View total check-ins, weight logs, and improvements.

/pr set deadlift <number>

Set new deadlift PR.

/pr set bench <number>

Set new bench press PR.

/pr set squat <number>

Set new squat PR.

/pr

View all personal records.

🏆 Leaderboard & Points

Command

Description

/leaderboard

Shows the top users based on points earned.

/points

View your current points.

🛠 Database Schema

The bot uses a PostgreSQL database to store user progress.

📌 Schema: database/schema.sql

💡 Contributing

Contributions are welcome!

Fork the repository

Create a new branch: git checkout -b feature-name

Commit changes: git commit -m "✨ Added new feature"

Push to GitHub: git push origin feature-name

Create a Pull Request

🐜 License

This project is open-source under the MIT License.

✉️ Contact

If you have any questions, reach out via GitHub Issues or contact 1TapDev.


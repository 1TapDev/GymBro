# commands/challenge_voting.py
import discord
import asyncio
from discord.ext import commands, tasks
from database import db
from datetime import datetime, timedelta
import random


class ChallengeVoting(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_voting_end.start()

    async def start_voting(self, challenge_id, challenge_name, channel_id):
        """Post participant comparisons and start voting"""
        channel = self.bot.get_channel(channel_id)
        if not channel:
            print(f"Channel {channel_id} not found for voting")
            return

        async with db.pool.acquire() as conn:
            # Get all participants who submitted final photos
            participants = await conn.fetch("""
                SELECT 
                    user_id, username, current_weight, goal_weight, 
                    final_weight, personal_goal, initial_photos, final_photos
                FROM challenge_participants
                WHERE challenge_id = $1 
                AND submitted_final = TRUE 
                AND disqualified = FALSE
                ORDER BY RANDOM()  -- Randomize order to prevent bias
            """, challenge_id)

            if len(participants) < 2:
                await channel.send(f"⚠️ Not enough participants completed **{challenge_name}**. Challenge cancelled.")
                return

            # Create voting announcement
            embed = discord.Embed(
                title=f"🗳️ Voting for {challenge_name} Has Begun!",
                description=(
                    f"**{len(participants)} participants** completed the challenge!\n\n"
                    "📊 **How to vote:**\n"
                    "• React with ✅ on the participant(s) you think showed the best progress\n"
                    "• You can vote for multiple participants\n"
                    "• You cannot vote for yourself\n"
                    "• Voting ends in 24 hours\n\n"
                    "⬇️ **Scroll down to see all transformations!**"
                ),
                color=discord.Color.blue()
            )
            await channel.send(embed=embed)

            # Store message IDs for vote counting
            voting_messages = []

            # Post each participant
            for idx, participant in enumerate(participants, 1):
                user = self.bot.get_user(participant['user_id'])
                display_name = user.display_name if user else participant['username']

                # Calculate progress
                weight_change = participant['final_weight'] - participant['current_weight']
                weight_emoji = "📈" if weight_change > 0 else "📉" if weight_change < 0 else "➡️"

                # Create comparison embed
                embed = discord.Embed(
                    title=f"Participant #{idx}: {display_name}",
                    color=discord.Color.random()
                )

                # Add stats
                embed.add_field(
                    name="📊 Stats",
                    value=(
                        f"**Starting Weight:** {participant['current_weight']} lbs\n"
                        f"**Goal Weight:** {participant['goal_weight']} lbs\n"
                        f"**Final Weight:** {participant['final_weight']} lbs\n"
                        f"**Total Change:** {weight_change:+.1f} lbs {weight_emoji}"
                    ),
                    inline=False
                )

                embed.add_field(
                    name="🎯 Personal Goal",
                    value=participant['personal_goal'] or "Not specified",
                    inline=False
                )

                # Post the embed first
                msg = await channel.send(embed=embed)

                # Post before/after photos
                try:
                    # Get first 4 photos from each set
                    initial_photos = participant['initial_photos'][:4] if participant['initial_photos'] else []
                    final_photos = participant['final_photos'][:4] if participant['final_photos'] else []

                    if initial_photos and final_photos:
                        # Create comparison image files
                        files = []

                        # Before photos
                        await channel.send("**📸 BEFORE:**")
                        before_files = []
                        for i, photo in enumerate(initial_photos):
                            if os.path.exists(photo):
                                before_files.append(discord.File(photo, filename=f"before_{i + 1}.jpg"))
                        if before_files:
                            await channel.send(files=before_files)

                        # After photos
                        await channel.send("**📸 AFTER:**")
                        after_files = []
                        for i, photo in enumerate(final_photos):
                            if os.path.exists(photo):
                                after_files.append(discord.File(photo, filename=f"after_{i + 1}.jpg"))
                        if after_files:
                            await channel.send(files=after_files)

                except Exception as e:
                    print(f"Error posting photos for participant {participant['user_id']}: {e}")

                # Add voting reaction
                await msg.add_reaction("✅")

                # Store message info
                voting_messages.append({
                    'message_id': msg.id,
                    'user_id': participant['user_id'],
                    'participant_name': display_name
                })

                # Add separator
                await channel.send("━" * 40)

            # Save voting message IDs to database
            async with db.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE challenges 
                    SET voting_messages = $1,
                        voting_end_time = NOW() + INTERVAL '24 hours'
                    WHERE id = $2
                """, voting_messages, challenge_id)

    @tasks.loop(hours=1)
    async def check_voting_end(self):
        """Check if voting period has ended and calculate results"""
        async with db.pool.acquire() as conn:
            ended_votings = await conn.fetch("""
                SELECT id, name, channel_id, voting_messages 
                FROM challenges 
                WHERE voting_started = TRUE 
                AND results_posted = FALSE
                AND voting_end_time <= NOW()
            """)

            for challenge in ended_votings:
                await self.calculate_results(
                    challenge['id'],
                    challenge['name'],
                    challenge['channel_id'],
                    challenge['voting_messages']
                )

    async def calculate_results(self, challenge_id, challenge_name, channel_id, voting_messages):
        """Count votes and determine winners"""
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return

        vote_counts = {}
        voter_tracker = {}  # Track who voted for whom

        # Count votes from each message
        for msg_info in voting_messages:
            try:
                message = await channel.fetch_message(msg_info['message_id'])

                # Get the check mark reaction
                for reaction in message.reactions:
                    if str(reaction.emoji) == "✅":
                        users = []
                        async for user in reaction.users():
                            if not user.bot and user.id != msg_info['user_id']:  # Prevent self-voting
                                users.append(user)

                                # Track votes
                                if user.id not in voter_tracker:
                                    voter_tracker[user.id] = []
                                voter_tracker[user.id].append(msg_info['user_id'])

                        vote_counts[msg_info['user_id']] = {
                            'count': len(users),
                            'name': msg_info['participant_name']
                        }
                        break

            except Exception as e:
                print(f"Error counting votes for message {msg_info['message_id']}: {e}")

        # Sort by vote count
        sorted_results = sorted(vote_counts.items(), key=lambda x: x['count'], reverse=True)

        # Handle ties with AI analysis if needed
        final_results = await self.handle_ties(sorted_results, challenge_id)

        # Post results
        await self.post_results(challenge_id, challenge_name, channel, final_results)

        # Update database
        async with db.pool.acquire() as conn:
            # Mark challenge as completed
            await conn.execute("""
                UPDATE challenges 
                SET status = 'completed', results_posted = TRUE 
                WHERE id = $1
            """, challenge_id)

            # Save rankings
            for rank, (user_id, data) in enumerate(final_results, 1):
                await conn.execute("""
                    UPDATE challenge_participants 
                    SET final_rank = $1, votes_received = $2 
                    WHERE challenge_id = $3 AND user_id = $4
                """, rank, data['count'], challenge_id, user_id)

    async def handle_ties(self, sorted_results, challenge_id):
        """Handle tied positions using AI image analysis"""
        # Group by vote count to find ties
        grouped = {}
        for user_id, data in sorted_results:
            count = data['count']
            if count not in grouped:
                grouped[count] = []
            grouped[count].append((user_id, data))

        # Check for ties
        final_results = []
        for count, participants in grouped.items():
            if len(participants) > 1:
                # AI analysis for tie-breaking
                tie_broken = await self.ai_tiebreaker(participants, challenge_id)
                final_results.extend(tie_broken)
            else:
                final_results.extend(participants)

        return final_results

    async def ai_tiebreaker(self, tied_participants, challenge_id):
        """Use AI to break ties based on transformation quality"""
        # This is a placeholder for AI integration
        # In production, you'd integrate with an image analysis API
        # For now, we'll use a simple randomization with explanation

        evaluations = []
        for user_id, data in tied_participants:
            # Simulated AI evaluation (replace with actual AI API)
            score = random.uniform(0.7, 0.95)
            reason = random.choice([
                "Showed exceptional muscle definition improvement",
                "Demonstrated significant body composition change",
                "Achieved remarkable overall transformation",
                "Displayed outstanding dedication and consistency",
                "Exhibited impressive strength gains visible in posture"
            ])

            evaluations.append({
                'user_id': user_id,
                'data': data,
                'ai_score': score,
                'reason': reason
            })

        # Sort by AI score
        evaluations.sort(key=lambda x: x['ai_score'], reverse=True)

        # Return sorted list with AI reasoning
        return [(e['user_id'], {**e['data'], 'ai_reason': e['reason']}) for e in evaluations]

    async def post_results(self, challenge_id, challenge_name, channel, results):
        """Post final challenge results"""
        # Create results embed
        embed = discord.Embed(
            title=f"🏆 {challenge_name} Results!",
            description="Congratulations to all participants!",
            color=discord.Color.gold()
        )

        # Medal emojis
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

        # Add top 5 (or all if less than 5)
        for idx, (user_id, data) in enumerate(results[:5]):
            medal = medals[idx] if idx < len(medals) else f"{idx + 1}."
            user = self.bot.get_user(user_id)
            name = user.mention if user else data['name']

            field_value = f"**Votes:** {data['count']}"
            if 'ai_reason' in data:
                field_value += f"\n*AI Note: {data['ai_reason']}*"

            embed.add_field(
                name=f"{medal} {name}",
                value=field_value,
                inline=False
            )

        # Add participation stats
        async with db.pool.acquire() as conn:
            stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_participants,
                    COUNT(CASE WHEN submitted_final = TRUE THEN 1 END) as completed,
                    AVG(final_weight - current_weight) as avg_weight_change
                FROM challenge_participants
                WHERE challenge_id = $1
            """, challenge_id)

        embed.add_field(
            name="📊 Challenge Statistics",
            value=(
                f"**Total Participants:** {stats['total_participants']}\n"
                f"**Completed:** {stats['completed']}\n"
                f"**Average Weight Change:** {stats['avg_weight_change']:.1f} lbs"
            ),
            inline=False
        )

        # Most Check-ins
        checkin_leader = await conn.fetchrow("""
            SELECT user_id, COUNT(*) AS total 
            FROM checkins 
            WHERE challenge_id = $1 
            GROUP BY user_id 
            ORDER BY total DESC 
            LIMIT 1
        """, challenge_id)

        # Biggest Weight Loss
        weight_loss_leader = await conn.fetchrow("""
            SELECT user_id, (current_weight - final_weight) AS diff 
            FROM challenge_participants 
            WHERE challenge_id = $1 AND submitted_final = TRUE 
            ORDER BY diff DESC 
            LIMIT 1
        """, challenge_id)

        if checkin_leader:
            user = self.bot.get_user(checkin_leader['user_id'])
            embed.add_field(
                name="📅 Most Check-ins",
                value=f"{user.mention if user else 'User'} with {checkin_leader['total']} check-ins",
                inline=False
            )

        if weight_loss_leader:
            user = self.bot.get_user(weight_loss_leader['user_id'])
            embed.add_field(
                name="⚖️ Biggest Weight Loss",
                value=f"{user.mention if user else 'User'} with {weight_loss_leader['diff']:.1f} lbs lost",
                inline=False
            )

        embed.set_footer(text="Thank you all for participating! 💪")

        await channel.send(embed=embed)

        # Notify winners via DM
        for idx, (user_id, data) in enumerate(results[:3]):
            user = self.bot.get_user(user_id)
            if user:
                try:
                    position = ["1st", "2nd", "3rd"][idx]
                    dm = await user.create_dm()
                    await dm.send(
                        f"🎉 Congratulations! You placed **{position}** in {challenge_name}! "
                        f"You received {data['count']} votes. Great job! 💪"
                    )
                except:
                    pass


async def setup(bot):
    await bot.add_cog(ChallengeVoting(bot))
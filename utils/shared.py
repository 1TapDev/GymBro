# commands/shared.py
import discord
import asyncio
import os
from database import db


async def send_final_photo_request(bot, user, challenge_id, challenge_name):
    """
    Send final photo collection DM to a user for challenge completion

    Args:
        bot: Discord bot instance
        user: Discord user object
        challenge_id: ID of the challenge
        challenge_name: Name of the challenge
    """
    try:
        print(f"📸 [SharedDM] Attempting to send final photo request to {user.name} (ID: {user.id})")

        dm_channel = await user.create_dm()
        print(f"📤 [SharedDM] DM channel created for {user.name}")

        # Create the initial embed
        embed = discord.Embed(
            title=f"🏁 {challenge_name} - Final Photo Submission",
            description=(
                "**Time to submit your final photos!** 📸\n\n"
                "Please upload your **4 final photos** in these poses:\n\n"
                "1️⃣ **Relaxed Front Pose**\n"
                "2️⃣ **Front Double Biceps**\n"
                "3️⃣ **Rear Double Biceps**\n"
                "4️⃣ **Relaxed Back Pose**\n\n"
                "📋 **Instructions:**\n"
                "• Upload each photo one at a time\n"
                "• I'll guide you through each pose\n"
                "• Take your time to get good shots!\n\n"
                "⏰ **Deadline:** 24 hours from now"
            ),
            color=discord.Color.orange()
        )
        embed.set_footer(text="Let's start with your first pose!")

        await dm_channel.send(embed=embed)
        print(f"✅ [SharedDM] Initial embed sent to {user.name}")

        # Start the photo collection process
        await collect_final_photos(bot, user, dm_channel, challenge_id, challenge_name)

    except discord.Forbidden:
        print(f"❌ [SharedDM] Cannot DM user {user.name} - DMs are disabled")
        raise
    except Exception as e:
        print(f"❌ [SharedDM] Error sending final photo request to {user.name}: {e}")
        raise


async def collect_final_photos(bot, user, dm_channel, challenge_id, challenge_name):
    """
    Handle the sequential collection of final photos from a user

    Args:
        bot: Discord bot instance
        user: Discord user object
        dm_channel: DM channel object
        challenge_id: ID of the challenge
        challenge_name: Name of the challenge
    """
    try:
        def photo_check(m):
            return m.author.id == user.id and m.channel == dm_channel and m.attachments

        def text_check(m):
            return m.author.id == user.id and m.channel == dm_channel and not m.attachments

        photos = []

        # Pose instructions for final photos
        pose_instructions = [
            {
                "pose": "Relaxed Front Pose",
                "instruction": "📸 Upload your **Relaxed Front Pose** photo:",
                "description": "Stand naturally facing the camera, arms at your sides"
            },
            {
                "pose": "Front Double Biceps",
                "instruction": "📸 Upload your **Front Double Biceps** photo:",
                "description": "Face the camera, flex both biceps with arms up"
            },
            {
                "pose": "Rear Double Biceps",
                "instruction": "📸 Upload your **Rear Double Biceps** photo:",
                "description": "Turn around, flex both biceps with back to camera"
            },
            {
                "pose": "Relaxed Back Pose",
                "instruction": "📸 Upload your **Relaxed Back Pose** photo:",
                "description": "Turn around, stand naturally with back to camera"
            }
        ]

        # Collect each photo sequentially
        for i, pose_data in enumerate(pose_instructions):
            # Send instruction for this pose
            pose_embed = discord.Embed(
                title=f"📸 Photo {i + 1}/4: {pose_data['pose']}",
                description=(
                    f"{pose_data['instruction']}\n\n"
                    f"💡 **Tip:** {pose_data['description']}\n\n"
                    "Upload your photo when ready!"
                ),
                color=discord.Color.blue()
            )
            await dm_channel.send(embed=pose_embed)

            # Wait for photo submission
            try:
                msg = await bot.wait_for("message", check=photo_check, timeout=3600)  # 1 hour timeout

                # Save the photo
                attachment = msg.attachments[0]
                photo_dir = f"challenge/{challenge_id}/final/{user.id}"
                os.makedirs(photo_dir, exist_ok=True)

                file_path = os.path.join(photo_dir, f"final_photo_{i + 1}_{attachment.filename}")
                await attachment.save(file_path)
                photos.append(file_path)

                await dm_channel.send(f"✅ Photo {i + 1}/4 received! Great work!")

                # Add separator between photos (except after the last one)
                if i < len(pose_instructions) - 1:
                    await asyncio.sleep(1)
                    await dm_channel.send("━" * 30)

            except asyncio.TimeoutError:
                await dm_channel.send(
                    "⏰ Photo submission timed out. Please try again by reacting to the original challenge message.")
                return

        # Ask for final weight
        await dm_channel.send("⚖️ What is your **final weight** in pounds? (e.g., 175.5)")

        try:
            weight_msg = await bot.wait_for("message", check=text_check, timeout=300)  # 5 minutes
            final_weight = float(weight_msg.content.strip())
        except (asyncio.TimeoutError, ValueError):
            await dm_channel.send("❌ Invalid weight or timeout. Please contact an admin to update your final weight.")
            final_weight = None

        # Update database with final submission
        async with db.pool.acquire() as conn:
            await conn.execute("""
                UPDATE challenge_participants 
                SET final_photos = $1, 
                    final_weight = $2, 
                    submitted_final = TRUE,
                    submission_date = NOW()
                WHERE challenge_id = $3 AND user_id = $4
            """, photos, final_weight, challenge_id, user.id)

        # Send completion confirmation
        completion_embed = discord.Embed(
            title="🎉 Final Submission Complete!",
            description=(
                f"**Challenge:** {challenge_name}\n\n"
                f"✅ **Photos Submitted:** {len(photos)}/4\n"
                f"⚖️ **Final Weight:** {final_weight} lbs\n\n"
                "Thank you for participating! 🏆\n"
                "Voting will begin once all participants have submitted their photos."
            ),
            color=discord.Color.green()
        )
        completion_embed.set_footer(text="Good luck in the voting phase!")

        await dm_channel.send(embed=completion_embed)
        print(f"🎉 [SharedDM] Final photo collection completed for {user.name}")

    except Exception as e:
        print(f"❌ [SharedDM] Error during photo collection for {user.name}: {e}")
        await dm_channel.send("❌ Something went wrong during photo submission. Please contact an admin for assistance.")
        raise
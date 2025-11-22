#!/usr/bin/env python3
"""
NeuroCrew Lab - Multi-Interface MVP Entry Point

Simple multi-interface architecture without legacy complexity.
"""

import asyncio
import signal
import sys
import threading
import logging
from pathlib import Path

from app.application import get_application, NeuroCrewApplication
from app.utils.logger import setup_logger

# Setup logging
logger = setup_logger("main_mvp", "INFO", log_file=Path("./data/logs/ncrew.log"))


def main():
    """Main entry point for NeuroCrew MVP Application."""
    try:
        logger.info("🚀 Starting NeuroCrew Lab MVP (Multi-Interface)...")
        logger.info(f"Python: {sys.version}")

        # Run the async main function
        asyncio.run(async_main())

    except KeyboardInterrupt:
        logger.info("Application stopped by user (Ctrl+C)")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        sys.exit(1)


async def async_main():
    """Async main function."""
    # Get application instance
    app = get_application()

    # Initialize application (no interfaces required)
    if not await app.initialize():
        logger.error("❌ Failed to initialize application")
        sys.exit(1)

    # Setup signal handlers for graceful shutdown
    setup_signal_handlers(app)

    # Start web server in separate thread (always available)
    web_thread = threading.Thread(target=run_web_server, name="web_server", daemon=True)
    web_thread.start()
    logger.info("🌐 Web server thread started on port 8080")

    # Start application with interfaces
    if not await app.start():
        logger.error("❌ Failed to start application")
        sys.exit(1)

    # Log startup status
    status = app.get_status()
    logger.info(f"📊 Application Status: {status}")

    # Run main application loop (simplified for MVP)
    await run_application_loop(app)


def run_web_server():
    """Run web server in separate thread."""
    try:
        from app.interfaces.web_server import app as flask_app

        logger.info("🌐 Starting web server on http://localhost:8080")
        # Simple Flask server for MVP
        flask_app.run(host="0.0.0.0", port=8080, use_reloader=False, debug=False)
    except Exception as e:
        logger.error(f"Web server error: {e}")


def setup_signal_handlers(app: NeuroCrewApplication):
    """Setup signal handlers for graceful shutdown."""
    def signal_handler(signum, frame):
        logger.info(f"🛑 Received signal {signum}, initiating shutdown...")
        asyncio.create_task(shutdown_application(app))

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def run_application_loop(app: NeuroCrewApplication):
    """Simplified application loop for MVP."""
    try:
        logger.info("🔄 Application is running... (Press Ctrl+C to stop)")

        # Simple running loop with periodic status checks
        check_counter = 0
        while app.is_running:
            await asyncio.sleep(5)  # Check every 5 seconds

            check_counter += 1
            if check_counter % 12 == 0:  # Log status every minute
                status = app.get_status()
                active_interfaces = len([k for k, v in status["interfaces"].items() if v == "active"])
                logger.info(f"📊 Status: Running mode={status['application']['operation_mode']}, "
                           f"Active interfaces={active_interfaces}")

    except asyncio.CancelledError:
        logger.info("Application loop cancelled")
    except Exception as e:
        logger.error(f"Error in application loop: {e}")


async def shutdown_application(app: NeuroCrewApplication):
    """Graceful shutdown of the application."""
    try:
        logger.info("🛑 Initiating graceful shutdown...")

        if await app.stop():
            logger.info("✅ Graceful shutdown completed")
        else:
            logger.error("❌ Shutdown completed with errors")
    except Exception as e:
        logger.error(f"❌ Error during shutdown: {e}")
    finally:
        logger.info("👋 NeuroCrew Lab MVP stopped")


if __name__ == "__main__":
    main()
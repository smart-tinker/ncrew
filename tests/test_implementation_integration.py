"""
Integration tests for the new multi-interface implementation.

Tests actual NeuroCrewApplication with real components.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from app.application import NeuroCrewApplication, get_application
from app.config import Config


class TestImplementationIntegration:
    """Integration tests for the actual implementation."""

    @pytest.mark.asyncio
    async def test_real_application_initialization(self):
        """Test real NeuroCrewApplication initialization."""
        app = NeuroCrewApplication()

        # Mock connector availability to ensure initialization succeeds even if tools are missing
        with patch("app.core.agent_coordinator.AgentCoordinator._validate_cli_command", return_value=True):
            # Should initialize without interfaces
            success = await app.initialize()
            
        assert success is True
        assert app.ncrew_lab is not None
        assert app.operation_mode.value in ["headless", "telegram", "web", "multi"]
        assert not app.is_running  # Not started yet

        # Verify core components are properly initialized
        assert hasattr(app.ncrew_lab, 'agent_coordinator')
        assert hasattr(app.ncrew_lab, 'session_manager')
        assert hasattr(app.ncrew_lab, 'dialogue_orchestrator')

    @pytest.mark.asyncio
    async def test_operation_mode_detection(self):
        """Test operation mode detection logic."""
        app = NeuroCrewApplication()

        with patch('app.application.Config.MAIN_BOT_TOKEN', 'fake_token'), \
             patch('app.application.Config.TARGET_CHAT_ID', '123456789'), \
             patch("app.core.agent_coordinator.AgentCoordinator._validate_cli_command", return_value=True):

            await app.initialize()
            # With Telegram config, should detect multi_interface mode
            assert app.operation_mode.value in ["telegram", "multi"]

    @pytest.mark.asyncio
    async def test_application_lifecycle(self):
        """Test complete application lifecycle."""
        app = NeuroCrewApplication()

        # Initialize
        with patch("app.core.agent_coordinator.AgentCoordinator._validate_cli_command", return_value=True):
            assert await app.initialize()
        
        assert not app.is_running

        # Mock interfaces for testing
        with patch.object(app, '_start_telegram_interface', return_value=True), \
             patch.object(app, '_start_web_interface', return_value=True):

            # Start application
            assert await app.start()
            assert app.is_running

            # Check status
            status = app.get_status()
            assert status["application"]["running"] is True
            assert status["application"]["ncrew_engine_initialized"] is True

            # Stop application
            assert await app.stop()
            assert not app.is_running

    @pytest.mark.asyncio
    async def test_headless_mode_operation(self):
        """Test operation in headless mode."""
        app = NeuroCrewApplication()

        with patch('app.application.Config.MAIN_BOT_TOKEN', ''), \
             patch('app.application.Config.TARGET_CHAT_ID', '0'), \
             patch("app.core.agent_coordinator.AgentCoordinator._validate_cli_command", return_value=True):

            await app.initialize()
            assert app.operation_mode.value == "headless"

            # Should start successfully in headless mode
            assert await app.start()
            assert app.is_running

            status = app.get_status()
            assert status["application"]["operation_mode"] == "headless"

    @pytest.mark.asyncio
    async def test_message_processing_flow(self):
        """Test end-to-end message processing."""
        app = NeuroCrewApplication()
        with patch("app.core.agent_coordinator.AgentCoordinator._validate_cli_command", return_value=True):
            await app.initialize()

        # Start application (mock interfaces)
        with patch.object(app, '_start_telegram_interface', return_value=True), \
             patch.object(app, '_start_web_interface', return_value=True):
            await app.start()
            assert app.is_running

        # Mock NeuroCrewLab.handle_message
        from app.config import RoleConfig

        mock_role = RoleConfig(
            role_name="test_role",
            display_name="Test Role",
            telegram_bot_name="test_bot",
            prompt_file="test.md",
            agent_type="test_agent",
            cli_command="test",
            description="Test role"
        )

        mock_responses = [
            (mock_role, "Response from role 1"),
            (mock_role, "Response from role 2")
        ]

        async def mock_handle_message(chat_id, user_text):
            for response in mock_responses:
                yield response

        app.ncrew_lab.handle_message = mock_handle_message

        # Mock interface response sending
        with patch.object(app, '_send_response_to_interface', return_value=True):

            # Process message
            success = await app.process_message("web", 123456, "Test message")
            assert success is True

    @pytest.mark.asyncio
    async def test_interface_failure_handling(self):
        """Test graceful handling of interface failures."""
        app = NeuroCrewApplication()
        with patch("app.core.agent_coordinator.AgentCoordinator._validate_cli_command", return_value=True):
            await app.initialize()

        # Start with mock interfaces
        with patch.object(app, '_start_telegram_interface', return_value=True), \
             patch.object(app, '_start_web_interface', return_value=True):

            await app.start()
            assert app.is_running

        # Simulate Telegram interface failure
        error = Exception("Telegram API error")
        await app.handle_interface_failure("telegram", error)

        status = app.get_status()
        assert status["interfaces"]["telegram"] == "error"
        # App should still be running
        assert app.is_running

    @pytest.mark.asyncio
    async def test_get_application_singleton(self):
        """Test application singleton pattern."""
        app1 = get_application()
        app2 = get_application()

        # Should return the same instance
        assert app1 is app2
        assert isinstance(app1, NeuroCrewApplication)

    @pytest.mark.asyncio
    async def test_configuration_integration(self):
        """Test integration with existing configuration system."""
        app = NeuroCrewApplication()
        with patch("app.core.agent_coordinator.AgentCoordinator._validate_cli_command", return_value=True):
            await app.initialize()

        # Check if it can access existing configuration
        roles = Config.get_available_roles()
        assert len(roles) > 0

        status = app.get_status()
        assert "roles" in status
        assert status["roles"]["total_loaded"] > 0

    @pytest.mark.asyncio
    async def test_error_handling_during_initialization(self):
        """Test error handling during application initialization."""
        app = NeuroCrewApplication()

        # Mock NeuroCrewLab to raise an exception
        with patch('app.application.NeuroCrewLab', side_effect=Exception("Initialization error")):
            success = await app.initialize()
            assert success is False

        # Application should still be in a valid state
        assert app.ncrew_lab is None


class TestImplementationCompatibility:
    """Test compatibility with existing system."""

    @pytest.mark.asyncio
    async def test_backward_compatibility_with_existing_config(self):
        """Test that new implementation works with existing configuration."""
        # Load existing roles
        roles = Config.get_available_roles()
        assert len(roles) > 0

        # Check if we have Telegram configuration
        telegram_available = bool(Config.MAIN_BOT_TOKEN and Config.TARGET_CHAT_ID)

        app = NeuroCrewApplication()
        await app.initialize()

        if telegram_available:
            # Should detect that Telegram is available
            assert app.operation_mode.value in ["telegram", "multi"]
        else:
            # Should work without Telegram
            assert app.operation_mode.value in ["headless", "web", "multi"]

    def test_import_compatibility(self):
        """Test that imports work with existing system."""
        # These imports should work without issues
        from app.application import NeuroCrewApplication
        from app.config import Config
        from app.core.engine import NeuroCrewLab

        # Classes should be properly defined
        assert NeuroCrewApplication is not None
        assert Config is not None
        assert NeuroCrewLab is not None

    @pytest.mark.asyncio
    async def test_component_integration(self):
        """Test integration with existing NeuroCrew components."""
        app = NeuroCrewApplication()
        with patch("app.core.agent_coordinator.AgentCoordinator._validate_cli_command", return_value=True):
            await app.initialize()

        # Verify existing components are accessible
        assert hasattr(app.ncrew_lab, 'agent_coordinator')
        assert hasattr(app.ncrew_lab, 'session_manager')
        assert hasattr(app.ncrew_lab, 'dialogue_orchestrator')
        assert hasattr(app.ncrew_lab, 'storage')

        # Verify they are properly initialized
        assert app.ncrew_lab.agent_coordinator is not None
        assert app.ncrew_lab.session_manager is not None
        assert app.ncrew_lab.dialogue_orchestrator is not None


if __name__ == "__main__":
    # Quick integration test runner
    async def run_integration_tests():
        print("=== Running Integration Tests ===")

        test_instance = TestImplementationIntegration()
        compatibility_instance = TestImplementationCompatibility()

        # List of test methods to run
        test_methods = [
            test_instance.test_real_application_initialization,
            test_instance.test_application_lifecycle,
            test_instance.test_headless_mode_operation,
            test_instance.test_message_processing_flow,
            test_instance.test_interface_failure_handling,
            test_instance.test_get_application_singleton,
            test_instance.test_configuration_integration,
            test_instance.test_error_handling_during_initialization,
            compatibility_instance.test_backward_compatibility_with_existing_config,
            compatibility_instance.test_import_compatibility,
            compatibility_instance.test_component_integration
        ]

        passed = 0
        total = len(test_methods)

        for test_method in test_methods:
            try:
                await test_method()
                print(f"✅ {test_method.__name__} - PASSED")
                passed += 1
            except Exception as e:
                print(f"❌ {test_method.__name__} - FAILED: {e}")

        print(f"\nIntegration Test Results: {passed}/{total} tests passed")
        return passed == total

    # Run the tests
    success = asyncio.run(run_integration_tests())
    if success:
        print("\n🚀 INTEGRATION TESTS ALL PASSED!")
    else:
        print("\n🚨 INTEGRATION TESTS FAILED!")
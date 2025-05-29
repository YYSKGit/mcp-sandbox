from typing import Dict, Any, Optional
from fastmcp import FastMCP
from mcp_sandbox.core.sandbox_modules.manager import SandboxManager
from mcp_sandbox.core.sandbox_modules.file_ops import SandboxFileOpsMixin
from mcp_sandbox.core.sandbox_modules.package import SandboxPackageMixin
from mcp_sandbox.core.sandbox_modules.records import SandboxRecordsMixin
from mcp_sandbox.core.sandbox_modules.execution import SandboxExecutionMixin
from mcp_sandbox.utils.config import DEFAULT_DOCKER_IMAGE

class SandboxEnvironment(
    SandboxManager, SandboxFileOpsMixin, SandboxPackageMixin, SandboxRecordsMixin, SandboxExecutionMixin
):
    pass

class SandboxToolsPlugin:
    """Expose sandbox operations as MCP tools for Python code execution."""
    
    def __init__(self, base_image: str = DEFAULT_DOCKER_IMAGE):
        self.sandbox_env = SandboxEnvironment(base_image=base_image)
        self.mcp = FastMCP("Python Sandbox Executor")
        self.user_context = {}
        self._register_tools()
    
    def set_user_context(self, user_id: str):
        """Set the current user context for authorization"""
        self.user_context["user_id"] = user_id
    
    def get_current_user_id(self) -> str:
        """Get the current user ID from context
        
        When authentication is disabled, returns the default user ID from config"""
        from mcp_sandbox.utils.config import REQUIRE_AUTH, DEFAULT_USER_ID
        
        # If authentication is disabled, return default user ID
        if not REQUIRE_AUTH:
            return DEFAULT_USER_ID
        
        # Otherwise return from user context
        return self.user_context.get("user_id")
    
    def validate_sandbox_access(self, sandbox_id: str) -> bool:
        """Validate if the current user has access to the sandbox"""
        from mcp_sandbox.db.database import db
        
        user_id = self.get_current_user_id()
        if not user_id:
            return False
        
        return db.is_sandbox_owner(user_id, sandbox_id)
    
    def _register_tools(self):
        """Register all MCP tools"""

        @self.mcp.tool(
            name="list_sandboxes",
            description="Lists all existing Python sandboxes and their status. Each item also includes installed Python packages."
        )
        def list_sandboxes() -> list:
            # Get user ID
            user_id = self.get_current_user_id()
            
            # Call list_user_sandboxes method in sandbox_modules
            return self.sandbox_env.list_user_sandboxes(user_id)

        @self.mcp.tool(
            name="create_sandbox", 
            description="Creates a new Python sandbox and returns its ID for subsequent operations. Optional parameter: name (string) - Custom name for the sandbox"
        )
        def create_sandbox(name: Optional[str] = None) -> dict:
            # Get user ID
            user_id = self.get_current_user_id()
            
            # Call create_user_sandbox method in sandbox_modules
            return self.sandbox_env.create_user_sandbox(user_id, name)

        @self.mcp.tool(
            name="install_package_in_sandbox",
            description="Installs a Python package in the specified sandbox. Parameters: sandbox_id (string), package_name (string)"
        )
        def install_package_in_sandbox(sandbox_id: str, package_name: str) -> Dict[str, Any]:
            # Validate sandbox access
            if not self.validate_sandbox_access(sandbox_id):
                return {"error": "Access denied. You don't have permission to access this sandbox."}
            
            return self.sandbox_env.install_package(sandbox_id, package_name)

        @self.mcp.tool(
            name="check_package_installation_status",
            description="Checks the installation status of a package in a sandbox. Parameters: sandbox_id (string), package_name (string)"
        )
        def check_package_installation_status(sandbox_id: str, package_name: str) -> Dict[str, Any]:
            # Validate sandbox access
            if not self.validate_sandbox_access(sandbox_id):
                return {"error": "Access denied. You don't have permission to access this sandbox."}
            
            return self.sandbox_env.check_package_status(sandbox_id, package_name)

        @self.mcp.tool(
            name="execute_python_code", 
            description="Executes Python code in a sandbox and returns results with links to generated files. Parameters: sandbox_id (string) - The sandbox ID to use, code (string) - The Python code to execute"
        )
        def execute_python_code(sandbox_id: str, code: str) -> Dict[str, Any]:
            # Validate sandbox access
            if not self.validate_sandbox_access(sandbox_id):
                return {"error": "Access denied. You don't have permission to access this sandbox."}
            
            return self.sandbox_env.execute_python_code(sandbox_id, code)

        @self.mcp.tool(
            name="execute_terminal_command",
            description="Executes a terminal command in the specified sandbox. Parameters: sandbox_id (string), command (string). Returns stdout, stderr, exit_code."
        )
        def execute_terminal_command(sandbox_id: str, command: str) -> Dict[str, Any]:
            # Verify sandbox access permissions
            if not self.validate_sandbox_access(sandbox_id):
                return {
                    "stdout": "",
                    "stderr": "Access denied. You don't have permission to access this sandbox.",
                    "exit_code": -1
                }
            
            # Call execute_terminal_command method in sandbox_modules
            return self.sandbox_env.execute_terminal_command(sandbox_id, command)

        @self.mcp.tool(
            name="upload_file_to_sandbox",
            description="Uploads a file from your local computer to the specified sandbox. Parameters: sandbox_id (string), local_file_path (string) - The full path of the file on your local computer to be uploaded, dest_path (string, optional, default: /app/results) - The target folder path in the sandbox, the uploaded file will be saved here with its original name."
        )
        def upload_file_to_sandbox(sandbox_id: str, local_file_path: str, dest_path: str = "/app/results") -> dict:
            # Validate sandbox access
            if not self.validate_sandbox_access(sandbox_id):
                return {"error": "Access denied. You don't have permission to access this sandbox."}
            
            return self.sandbox_env.upload_file_to_sandbox(sandbox_id, local_file_path, dest_path)

        @self.mcp.tool(
            name="delete_sandboxes",
            description="Deletes one or more specified Python sandboxes. Parameters: sandbox_ids (list[string]) - A list of sandbox IDs to delete."
        )
        def delete_sandboxes(sandbox_ids: list) -> Dict[str, Any]:
            """
            删除一个或多个指定的沙盒。

            Args:
                sandbox_ids: 要删除的沙盒 ID 列表。

            Returns:
                一个包含每个沙盒删除结果的字典。
            """
            results = {}
            user_id = self.get_current_user_id() # 获取当前用户ID

            # 确保输入是列表
            if not isinstance(sandbox_ids, list):
                return {"error": "参数 'sandbox_ids' 必须是一个列表。"}

            for sandbox_id in sandbox_ids:
                # 验证沙盒访问权限
                if not self.validate_sandbox_access(sandbox_id):
                    results[sandbox_id] = {"success": False, "message": "访问被拒绝。您无权删除此沙盒。"}
                    continue

                try:
                    # 调用 manager 中的新方法删除沙盒
                    result = self.sandbox_env.delete_sandbox_by_id(sandbox_id)
                    results[sandbox_id] = result
                except Exception as e:
                    # 记录异常并返回错误信息
                    from mcp_sandbox.utils.config import logger
                    logger.error(f"删除沙盒 {sandbox_id} 时发生意外错误: {e}", exc_info=True)
                    results[sandbox_id] = {"success": False, "message": f"删除时发生意外错误: {str(e)}"}

            return results

import os
import ast
import sys

# 排除目录列表
EXCLUDE_DIRS = {'__pycache__', '.git', '.idea', 'venv', '.vscode', 'tools'}

def is_public_api(node):
    """判断是否为公开API (不以_开头)"""
    return not node.name.startswith('_') or node.name.startswith('__init__')

class StubVisitor(ast.NodeVisitor):
    def __init__(self):
        self.output = []
        self.indent_level = 0

    def _log(self, text):
        self.output.append("    " * self.indent_level + text)

    def visit_ClassDef(self, node):
        # 记录类定义 class ClassName(Base):
        bases = [ast.unparse(b) for b in node.bases]
        base_str = f"({', '.join(bases)})" if bases else ""
        self._log(f"class {node.name}{base_str}:")
        
        self.indent_level += 1
        
        # 提取 Docstring
        doc = ast.get_docstring(node)
        if doc:
            # 只取文档第一行，节省Token
            summary = doc.split('\n')[0]
            self._log(f'"""{summary}"""')

        # 遍历类内部节点
        has_content = False
        
        # 1. 提取 dataclass 字段 (AnnAssign)
        # 例如: hp: int
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                type_hint = ast.unparse(item.annotation)
                self._log(f"{item.target.id}: {type_hint}")
                has_content = True

        # 2. 提取方法
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                if is_public_api(item):
                    self.visit(item)
                    has_content = True
        
        if not has_content:
            self._log("...")
            
        self.indent_level -= 1
        self._log("") # 空行分隔

    def visit_FunctionDef(self, node):
        # 提取函数定义 def func(a: int) -> int:
        args = ast.unparse(node.args)
        returns = f" -> {ast.unparse(node.returns)}" if node.returns else ""
        
        # 提取 Docstring
        doc = ast.get_docstring(node)
        doc_str = f'  """{doc.split(chr(10))[0]}"""' if doc else ""
        
        self._log(f"def {node.name}({args}){returns}:{doc_str}")
        # 不打印函数体，只打印 ...
        # self._log("    ...") 

    def visit_Assign(self, node):
        # 提取全局常量 (仅限大写)
        # 例如: MAX_ROUNDS = 4
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.isupper():
                if node.value:
                    val = ast.unparse(node.value)
                    self._log(f"{target.id} = {val}")

def generate_project_stub(root_dir, output_file):
    output = []
    
    for root, dirs, files in os.walk(root_dir):
        # 过滤排除目录
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                rel_path = os.path.relpath(path, root_dir)
                
                output.append("=" * 40)
                output.append(f"FILE: {rel_path}")
                output.append("=" * 40)
                
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read())
                    
                    visitor = StubVisitor()
                    visitor.visit(tree)
                    output.extend(visitor.output)
                    output.append("\n")
                except Exception as e:
                    output.append(f"# Error parsing file: {e}\n")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(output))
    
    print(f"[OK] 项目存根已生成: {output_file}")
    print(f"[INFO] 文件大小: {os.path.getsize(output_file) / 1024:.2f} KB")

if __name__ == "__main__":
    # 获取项目根目录 (假设 tools 在根目录下)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(project_root, "project_context.txt")
    
    generate_project_stub(project_root, output_path)
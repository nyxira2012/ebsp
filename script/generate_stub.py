import os
import ast
import sys

import re

# 排除目录列表
EXCLUDE_DIRS = {'__pycache__', '.git', '.idea', 'venv', '.vscode', 'tools', 'tests', 'sim'}

def extract_hooks(root_dir):
    """扫描所有文件并提取以 HOOK_ 开头的字符串常量"""
    hooks = set()
    pattern = re.compile(r'HOOK_[A-Z_]+')
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            if file.endswith(".py"):
                with open(os.path.join(root, file), "r", encoding="utf-8", errors="ignore") as f:
                    hooks.update(pattern.findall(f.read()))
    return sorted(list(hooks))

def is_public_api(node):
    """判断是否为公开API (不以_开头)"""
    return not node.name.startswith('_') or node.name.startswith('__init__')

def shorten_type(t: str) -> str:
    """缩短类型提示: Optional[T] -> T | None, List[T] -> list[T]"""
    t = t.replace('Optional[', '').replace(']', ' | None') if 'Optional[' in t else t
    t = t.replace('List[', 'list[').replace('Dict[', 'dict[')
    return t

def truncate_val(val: str, max_len: int = 500) -> str:
    """截断过长的赋值内容，保留足够信息供 AI 了解数据结构"""
    if len(val) > max_len:
        return val[:max_len] + "...(truncated)"
    return val

class StubVisitor(ast.NodeVisitor):
    def __init__(self, filename=""):
        self.output = []
        self.indent_level = 0
        self.filename = filename

    def _log(self, text):
        if text.strip():
            self.output.append("  " * self.indent_level + text)

    def visit_ClassDef(self, node):
        bases = [shorten_type(ast.unparse(b)) for b in node.bases]
        base_str = f"({', '.join(bases)})" if bases else ""
        self._log(f"class {node.name}{base_str}:")
        
        self.indent_level += 1
        doc = ast.get_docstring(node)
        if doc:
            self._log(f'"""{doc.split(chr(10))[0]}"""')

        is_enum = any("Enum" in b for b in bases)
        has_content = False
        
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                type_hint = shorten_type(ast.unparse(item.annotation))
                self._log(f"{item.target.id}: {type_hint}")
                has_content = True
            elif is_enum and isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        val = truncate_val(ast.unparse(item.value), 200)
                        self._log(f"{target.id} = {val}")
                        has_content = True

        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                if is_public_api(item):
                    self.visit(item)
                    has_content = True
        
        if not has_content: self._log("...")
        self.indent_level -= 1

    def visit_FunctionDef(self, node):
        args = ast.unparse(node.args).replace('self, ', '').replace('self', '')
        returns = f" -> {shorten_type(ast.unparse(node.returns))}" if node.returns else ""
        doc = ast.get_docstring(node)
        
        # 提取关键信息：公式或第一行注释
        formula = ""
        if doc:
            lines = doc.split('\n')
            for line in lines:
                if "公式:" in line or "Formula:" in line:
                    formula = f" # {line.strip()}"
                    break
            if not formula:
                formula = f"  \"\"\"{lines[0].strip()}\"\"\""

        sig = f"def {node.name}({args}){returns}:{formula}"
        self._log(sig)

        # 对于计算类文件，显示函数体中的 return 语句
        is_calc_file = "calculator" in self.filename or "resolver" in self.filename
        if is_calc_file:
            self.indent_level += 1
            for item in node.body:
                if isinstance(item, ast.Return):
                    self._log(f"return {ast.unparse(item.value)}")
                elif isinstance(item, (ast.Assign, ast.AnnAssign)) and len(node.body) < 8:
                    # 如果函数很短，显示赋值语句（可能是中间公式）
                    self._log(ast.unparse(item))
            self.indent_level -= 1

    def visit_Assign(self, node):
        for target in node.targets:
            if isinstance(target, ast.Name):
                if target.id.isupper() or (target.id[0].isupper() and isinstance(node.value, ast.Name)):
                    val = truncate_val(ast.unparse(node.value), 500)
                    self._log(f"{target.id} = {val}")

def generate_project_stub(root_dir, output_file):
    output = []
    
    # 提取所有 Hooks 作为虚拟常量
    hooks = extract_hooks(root_dir)
    if hooks:
        output.append("--- VIRTUAL CONSTANTS: AVAILABLE HOOKS ---")
        for hook in hooks:
            output.append(f"{hook} = '{hook}'")
        output.append("")

    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            if file.endswith(".py") and file != "generate_stub.py":
                path = os.path.join(root, file)
                rel_path = os.path.relpath(path, root_dir)
                output.append(f"\n--- {rel_path} ---")
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        tree = ast.parse(f.read())
                    visitor = StubVisitor(filename=rel_path)
                    visitor.visit(tree)
                    output.extend(visitor.output)
                except Exception as e:
                    output.append(f"# Error: {e}")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(output).strip())
    
    print(f"[OK] 项目存根已生成: {output_file}")
    print(f"[INFO] 文件大小: {os.path.getsize(output_file) / 1024:.2f} KB")

if __name__ == "__main__":
    # 获取项目根目录 (假设 tools 在根目录下)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(project_root, "project_context.txt")
    
    generate_project_stub(project_root, output_path)
import re
from z3 import Z3Exception
from mythril.laser.smt import simplify
from mythril.laser.ethereum.svm import NodeFlags


def render_node(node):
    """
    渲染单个节点，提取第一个指令地址作为id，所有指令作为内容

    :param node: CFG节点对象
    :return: 包含id和content的字典
    """
    # 获取节点中所有状态的指令
    instructions = [state.get_current_instruction() for state in node.states]

    if not instructions:
        return {"id": str(node.start_addr), "content": ""}

    # 使用第一个指令的地址作为id
    first_instruction = instructions[0]
    node_id = first_instruction["address"]

    # 构建所有指令的内容
    code_lines = []
    for instruction in instructions:
        address = instruction["address"]
        opcode = instruction["opcode"]

        if opcode.startswith("PUSH"):
            # PUSH指令包含参数
            code_line = f"{address} {opcode} {instruction.get('argument', '')}"
        elif (
            opcode.startswith("JUMPDEST")
            and NodeFlags.FUNC_ENTRY in node.flags
            and address == node.start_addr
        ):
            # 函数入口点显示函数名
            code_line = node.function_name
        else:
            # 普通指令
            code_line = f"{address} {opcode}"

        # 简化长地址显示
        code_line = re.sub(r"([0-9a-f]{8})[0-9a-f]+", r"\1(...)", code_line)
        code_lines.append(code_line)

    return {"id": node_id, "content": "\n".join(code_lines)}


def render_edge(edge, node_id_mapping):
    """
    渲染单个边，使用重新渲染的节点id映射

    :param edge: CFG边对象
    :param node_id_mapping: 字典，原始节点uid到重新渲染的节点id的映射
    :return: 包含from和to的字典
    """
    # 获取原始的from和to节点uid
    original_from = edge.as_dict["from"]
    original_to = edge.as_dict["to"]

    # 使用映射表获取重新渲染的节点id
    rendered_from = node_id_mapping.get(original_from, original_from)
    rendered_to = node_id_mapping.get(original_to, original_to)

    # 处理条件标签（可选）
    condition_label = ""
    if edge.condition is not None:
        try:
            condition_label = str(simplify(edge.condition)).replace("\n", "")
        except Z3Exception:
            condition_label = str(edge.condition).replace("\n", "")

        # 简化数字显示
        condition_label = re.sub(
            r"([^_])([\d]{2}\d+)",
            lambda m: m.group(1) + hex(int(m.group(2))),
            condition_label,
        )

    # return {"from": rendered_from, "to": rendered_to, "condition": condition_label}
    return (rendered_from, rendered_to)


# 完整的处理流程
def extract_rendered_nodes_and_edges(statespace):
    """
    提取所有重新渲染的节点和边信息

    :param statespace: 状态空间对象
    :return: (rendered_nodes, rendered_edges) 元组
    """
    # 1. 渲染所有节点，并建立映射关系
    rendered_nodes = []
    node_id_mapping = {}  # 原始uid -> 新的node id

    for node_key, node in statespace.nodes.items():
        rendered_node = render_node(node)
        rendered_nodes.append(rendered_node)

        # 建立原始节点uid到新节点id的映射
        node_id_mapping[node_key] = rendered_node["id"]

    # 2. 基于新的节点id映射来渲染边
    rendered_edges = []
    for edge in statespace.edges:
        rendered_edge = render_edge(edge, node_id_mapping)
        rendered_edges.append(rendered_edge)

    return rendered_nodes, rendered_edges

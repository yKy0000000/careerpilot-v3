# 开源实践：LLVM/Clang 本地构建与 Assertion Crash 分析

> 技术栈：C++ / Clang / CMake / Ninja

## 环境构建

从源码构建 LLVM/Clang main 分支，配置 CMake/Ninja/MSVC 构建环境，启用 assertions，解决 Windows 下 MSVC 编码与本地构建工具运行问题。

## 问题复现

构造 `__builtin_nanf(L"")` 最小复现用例，复现其先触发 Sema 参数类型诊断、随后在 AST 常量求值阶段触发 `StringLiteral::getString()` 断言崩溃的问题。

## 源码分析

根据断言栈信息定位到 `StringLiteral::getString()` 的调用前置条件，进一步分析 `ExprConstant.cpp` 中 `TryEvaluateBuiltinNaN` 对 `__builtin_nan*` payload 的处理逻辑，理解编译器前端对内置函数常量表达式的求值路径。

## 回归验证

补充最小复现用例与 `clang -cc1 -verify` 测试，本地验证非单字节字符串应跳过 `__builtin_nan*` 常量折叠，避免断言崩溃。

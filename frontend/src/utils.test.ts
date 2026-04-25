import { describe, expect, it } from "vitest";
import { tildifyPath } from "./utils";

describe("tildifyPath", () => {
  it("collapses macOS home prefixes", () => {
    expect(tildifyPath("/Users/jingheng/Documents/Foo")).toBe("~/Documents/Foo");
    expect(tildifyPath("/Users/jane.doe/x")).toBe("~/x");
  });

  it("collapses Linux home prefixes", () => {
    expect(tildifyPath("/home/jingheng/projects/bar")).toBe("~/projects/bar");
    expect(tildifyPath("/root/code")).toBe("~/code");
    expect(tildifyPath("/root")).toBe("~");
  });

  it("collapses Windows home prefixes regardless of slash style", () => {
    expect(tildifyPath("C:\\Users\\Jane\\Documents\\Foo")).toBe("~\\Documents\\Foo");
    expect(tildifyPath("C:/Users/Jane/Documents/Foo")).toBe("~/Documents/Foo");
    expect(tildifyPath("D:\\Users\\jane")).toBe("~");
  });

  it("returns the original string when no home prefix matches", () => {
    expect(tildifyPath("/var/log/system.log")).toBe("/var/log/system.log");
    expect(tildifyPath(".openclaw/workspace")).toBe(".openclaw/workspace");
    expect(tildifyPath("")).toBe("");
  });

  it("does not match a username prefix without a separator", () => {
    expect(tildifyPath("/Users")).toBe("/Users");
    expect(tildifyPath("/home")).toBe("/home");
  });
});
